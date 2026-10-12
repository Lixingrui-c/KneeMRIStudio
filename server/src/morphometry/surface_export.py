import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import numpy as np


def _geometry(mesh):
    vertices = np.asarray(mesh.vertices_sub, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("Expected Nx3 vertices and Mx3 triangles")
    if not np.isfinite(vertices).all():
        raise ValueError("Nonfinite mesh coordinates")
    if faces.size and (faces.min() < 0 or faces.max() >= len(vertices)):
        raise ValueError("Invalid triangle vertex index")
    return vertices, faces


def _areas(vertices, faces, vox):
    triangles = (vertices * vox)[faces]
    return .5 * np.linalg.norm(np.cross(
        triangles[:, 1] - triangles[:, 0],
        triangles[:, 2] - triangles[:, 0]), axis=1)


def build_bone_coverage(bone, regions, vox):
    """regions: sequence of (name, scb mesh, final covered-face flags).

    Match exact vertices/triangles to the parent mesh, reject unmatched or
    contradictory labels. Repeated consistent tibial domain faces count once.
    """
    vertices, faces = _geometry(bone)
    vox = np.asarray(vox, dtype=np.float64)
    if vox.shape != (3,) or not np.isfinite(vox).all() or np.any(vox <= 0):
        raise ValueError("Invalid physical voxel spacing")
    vertex_ids = {tuple(v): i for i, v in enumerate(vertices)}
    face_ids = {tuple(sorted(f)): i for i, f in enumerate(faces)}
    if len(vertex_ids) != len(vertices) or len(face_ids) != len(faces):
        raise ValueError("Parent bone mesh is not deduplicated")
    face_class = np.zeros(len(faces), dtype=np.uint8)
    areas = _areas(vertices, faces, vox)
    audits = []
    for name, scb, flags in regions:
        sv, sf = _geometry(scb)
        if flags is None:
            raise ValueError(f"{name}: final coverage flags were not computed")
        flags = np.asarray(flags, dtype=bool)
        if flags.shape != (len(sf),):
            raise ValueError(f"{name}: coverage flag count mismatch")
        try:
            vi = np.array([vertex_ids[tuple(v)] for v in sv], dtype=np.int64)
            ids = np.array([face_ids[tuple(sorted(f))] for f in vi[sf]], dtype=np.int64)
        except KeyError as exc:
            raise ValueError(f"{name}: scb is not an exact subset of the bone mesh") from exc
        if len(np.unique(ids)) != len(ids):
            raise ValueError(f"{name}: duplicated scb faces")
        values = np.where(flags, 1, 2).astype(np.uint8)
        if np.any((face_class[ids] != 0) & (face_class[ids] != values)):
            raise ValueError(f"{name}: overlapping cartilage domains have conflicting coverage")
        source_areas = _areas(sv, sf, vox)
        if not np.allclose(source_areas, areas[ids], rtol=1e-10, atol=1e-10):
            raise ValueError(f"{name}: face areas changed during mapping")
        face_class[ids] = values
        tab = float(source_areas.sum())
        cab = float(source_areas[flags].sum())
        dab = float(source_areas[~flags].sum())
        audits.append({"name": name, "status": "available" if len(sf) else "empty_domain",
                       "faces": len(sf), "tAB_mm2": tab, "cAB_mm2": cab,
                       "dAB_mm2": dab, "FCL_percent": 100*dab/tab if tab else None})
    return {"vertices_sub": vertices, "faces": faces, "coverage_class": face_class,
            "audit": {"faces": len(faces), "regions": audits,
                      "union_tAB_mm2": float(areas[face_class != 0].sum()),
                      "union_cAB_mm2": float(areas[face_class == 1].sum()),
                      "union_dAB_mm2": float(areas[face_class == 2].sum())}}


def _array(parent, name, dtype, values, components=1):
    element = ET.SubElement(parent, "DataArray", type=dtype, Name=name,
                            NumberOfComponents=str(components), format="ascii")
    a = np.asarray(values)
    fmt = ".17g" if a.dtype.kind == "f" else "d"
    element.text = " ".join(format(x, fmt) for x in a.ravel())


def _write_vtp(path, vertices, faces, classes, bone_ids):
    root = ET.Element("VTKFile", type="PolyData", version="0.1", byte_order="LittleEndian")
    poly = ET.SubElement(root, "PolyData")
    piece = ET.SubElement(poly, "Piece", NumberOfPoints=str(len(vertices)),
                          NumberOfPolys=str(len(faces)), NumberOfVerts="0",
                          NumberOfLines="0", NumberOfStrips="0")
    ET.SubElement(piece, "PointData")
    cells = ET.SubElement(piece, "CellData", Scalars="coverage_rgb")
    _array(cells, "coverage_class", "UInt8", classes)
    _array(cells, "bone_label", "UInt8", bone_ids)
    colors = np.array([[180, 180, 180], [45, 190, 80], [230, 50, 50]], dtype=np.uint8)
    _array(cells, "coverage_rgb", "UInt8", colors[classes], 3)
    _array(ET.SubElement(piece, "Points"), "Points", "Float64", vertices, 3)
    polys = ET.SubElement(piece, "Polys")
    _array(polys, "connectivity", "Int64", faces)
    _array(polys, "offsets", "Int64", np.arange(1, len(faces)+1, dtype=np.int64)*3)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def export_coverage_surfaces(directory, payload, affine, vox):
    """Write femur, tibia, combined VTP and JSON audit. Publish audit last."""
    affine = np.asarray(affine, dtype=np.float64)
    vox = np.asarray(vox, dtype=np.float64)
    if affine.shape != (4, 4) or not np.isfinite(affine).all() or not np.allclose(affine[3], [0, 0, 0, 1]):
        raise ValueError("Invalid NIfTI affine")
    # Metrics use spacing-only geometry; shear would change physical areas.
    if not np.allclose(affine[:3, :3].T @ affine[:3, :3], np.diag(vox**2), rtol=1e-5, atol=1e-7):
        raise ValueError("Affine contains shear or spacing differs from metric vox size")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    audits = {}
    all_v, all_f, all_c, all_b = [], [], [], []
    offset = 0
    names = []
    with tempfile.TemporaryDirectory(prefix="coverage_", dir=directory) as tmp:
        tmp = Path(tmp)
        for name, label in (("femur", 1), ("tibia", 3)):
            item = payload[name]
            v = (item["vertices_sub"] - 1) @ affine[:3, :3].T + affine[:3, 3]
            f, c = item["faces"], item["coverage_class"]
            b = np.full(len(f), label, dtype=np.uint8)
            filename = f"{name}_coverage.vtp"
            _write_vtp(tmp / filename, v, f, c, b)
            names.append(filename)
            all_v.append(v); all_f.append(f+offset); all_c.append(c); all_b.append(b)
            offset += len(v)
            audits[name] = item["audit"]
        filename = "bone_coverage.vtp"
        _write_vtp(tmp / filename, np.vstack(all_v), np.vstack(all_f),
                   np.concatenate(all_c), np.concatenate(all_b))
        names.append(filename)
        manifest = {"schema_version": 1, "coordinate_system": "NIfTI RAS", "units": "mm",
                    "geometry": "metric bone mesh (largest connected component per bone), unsmoothed",
                    "cell_array": "coverage_class", "color_array": "coverage_rgb",
                    "classes": {"0": "outside reconstructed domain / not assessed",
                                "1": "cartilage covered", "2": "estimated full-thickness defect"},
                    "files": names.copy(), "bones": audits,
                    "note": "Union areas are not sums of overlapping 20-ROI area outputs."}
        (tmp / "coverage_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
        names.append("coverage_manifest.json")
        for filename in names:
            os.replace(tmp / filename, directory / filename)
    return manifest
