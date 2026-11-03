import json
from pathlib import Path
import os
import tempfile
import xml.etree.ElementTree as ET
import numpy as np
try:
    from .surface_export import _write_vtp, _array
except ImportError:
    from surface_export import _write_vtp, _array

def attach_thickness(item, regions):
    vi = {tuple(v): i for i,v in enumerate(item["vertices_sub"])}
    fi = {tuple(sorted(f)): i for i,f in enumerate(item["faces"])}
    c = item["coverage_class"]
    values = np.full(len(c), -1., dtype=float)
    valid = np.zeros(len(c), dtype=np.uint8)
    assigned = np.zeros(len(c), dtype=bool)
    for mesh, thickness, matched in regions:
        t, m = np.asarray(thickness,float), np.asarray(matched,bool)
        if t.shape != (len(mesh.vertices_sub),) or m.shape != t.shape:
            raise ValueError("Thickness vertex correspondence mismatch")
        ids_v = np.array([vi[tuple(v)] for v in mesh.vertices_sub],dtype=np.int64)
        ids = np.array([fi[tuple(sorted(f))] for f in ids_v[mesh.faces]],dtype=np.int64)
        samples = t[mesh.faces]
        ok = (m[mesh.faces] & np.isfinite(samples) & (samples >= 0)).all(axis=1) & (c[ids] == 1)
        defect = c[ids] == 2
        tv = np.full(len(ids), -1.,dtype=float)
        tv[ok] = samples[ok].mean(axis=1)
        tv[defect] = 0.
        flags = (ok | defect).astype(np.uint8)
        if np.any(assigned[ids] & ((valid[ids] != flags) | ~np.isclose(values[ids],tv,atol=1e-8,rtol=1e-6))):
            raise ValueError("Overlapping domains disagree on thickness")
        values[ids], valid[ids], assigned[ids] = tv, flags, True
    if np.any((c != 0) & ~assigned):
        raise ValueError("Missing thickness mapping on assessed faces")
    item["thickness_mm"], item["thickness_valid"] = values, valid

def export_thickness_surfaces(directory, payload, affine, knee_side):
    a = np.asarray(affine,float)
    if a.shape != (4,4) or not np.isfinite(a).all() or not np.allclose(a[3],[0,0,0,1]):
        raise ValueError("Invalid affine")
    if knee_side not in ("left","right"): raise ValueError("Invalid knee side")
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    manifest = dict(schema_version=1, coordinate_system="NIfTI RAS", units="mm",
        knee_side=knee_side, association="CellData", thickness_array="thickness_mm",
        valid_array="thickness_valid", coverage_array="coverage_class", invalid_sentinel=-1,
        definition="Covered face: mean of three matched final tAB vertex thickness samples. Defect face: zero.",
        note="Includes existing thickness interpolation and uncertainty correction. Validity is mapping/numeric validity, not clinical confidence. CSV retains its original vertex reductions.",
        classes={"0":"not assessed","1":"covered","2":"estimated full-thickness defect"},
        anatomical_axes_ras={"right":[1,0,0],"anterior":[0,1,0],"superior":[0,0,1]}, bones={})
    names, maxima = [], []
    with tempfile.TemporaryDirectory(prefix="thickness_",dir=directory) as temp:
        temp = Path(temp)
        for name,label in (("femur",1),("tibia",3)):
            item = payload[name]
            v = (item["vertices_sub"]-1) @ a[:3,:3].T + a[:3,3]
            f,c = item["faces"],item["coverage_class"]
            t,valid = item["thickness_mm"],item["thickness_valid"]
            filename = name+"_thickness.vtp"
            path = temp/filename
            _write_vtp(path,v,f,c,np.full(len(f),label,dtype=np.uint8))
            tree = ET.parse(path)
            cells = tree.getroot().find("./PolyData/Piece/CellData")
            cells.set("Scalars","thickness_mm")
            _array(cells,"thickness_mm","Float64",t)
            _array(cells,"thickness_valid","UInt8",valid)
            for key, dtype in (("roi_id","Int32"), ("fcl_percent","Float64"),
                               ("fcl_valid","UInt8"), ("roi_candidate_count","UInt8")):
                _array(cells,key,dtype,item[key])
            tree.write(path,encoding="utf-8",xml_declaration=True)
            measured = t[(c == 1) & (valid == 1)]
            if len(measured): maxima.append(float(measured.max()))
            domain = v[np.unique(f[c != 0])] if np.any(c != 0) else np.empty((0,3))
            manifest["bones"][name] = dict(file=filename, artifact=name+"_thickness",
                points=len(v),faces=len(f),
                invalid_covered_faces=int(np.count_nonzero((c==1)&(valid==0))),
                assessed_center_ras_mm=domain.mean(axis=0).tolist() if len(domain) else None,
                covered_thickness_range_mm=[float(measured.min()),float(measured.max())] if len(measured) else None)
            names.append(filename)
        manifest["regional_fcl"] = payload["femur"]["regional_fcl"]
        manifest["fcl_units"] = "%"
        manifest["fcl_display_range"] = [0,100]
        manifest["roi_display_rule"] = "Most member vertices per face, tie: lowest ROI id. Display partition only; original overlapping ROI metrics unchanged."
        manifest["shared_data_range_mm"] = [0.,max(maxima)] if maxima else None
        (temp/"thickness_manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False),encoding="utf-8")
        for name in names+["thickness_manifest.json"]:
            os.replace(temp/name,directory/name)
    return manifest


def attach_regional_fcl(item, regions, percentages, roi_names):
    """Display-only ownership: most member vertices, then lowest ROI id."""
    vi = {tuple(v): i for i,v in enumerate(item["vertices_sub"])}
    fi = {tuple(sorted(f)): i for i,f in enumerate(item["faces"])}
    n = len(item["faces"])
    votes = np.zeros((n, len(roi_names)), dtype=np.uint8)
    for mesh, masks in regions:
        vertex_ids = np.array([vi[tuple(v)] for v in mesh.vertices_sub],dtype=np.int64)
        ids = np.array([fi[tuple(sorted(f))] for f in vertex_ids[mesh.faces]],dtype=np.int64)
        for roi,mask in masks.items():
            if not 1 <= int(roi) <= len(roi_names): raise ValueError("Unknown ROI id")
            mask=np.asarray(mask,bool)
            if mask.shape != (len(mesh.vertices_sub),): raise ValueError("ROI mask shape mismatch")
            score=mask[mesh.faces].sum(axis=1).astype(np.uint8)
            votes[ids,roi-1]=np.maximum(votes[ids,roi-1],score)
    inside=item["coverage_class"]!=0
    assigned=inside & (votes.max(axis=1)>0)
    roi_id=np.zeros(n,dtype=np.int32)
    roi_id[assigned]=votes[assigned].argmax(axis=1)+1
    values=np.full(n,-1.,dtype=float);valid=np.zeros(n,dtype=np.uint8)
    percentages=np.asarray(percentages,float)
    if percentages.shape!=(len(roi_names),): raise ValueError("FCL shape mismatch")
    for r in range(1,len(roi_names)+1):
        if np.isfinite(percentages[r-1]) and 0<=percentages[r-1]<=100:
            cells=roi_id==r;values[cells]=percentages[r-1];valid[cells]=1
    item["roi_id"],item["fcl_percent"],item["fcl_valid"]=roi_id,values,valid
    item["roi_candidate_count"]=(votes>0).sum(axis=1).astype(np.uint8)
    item["regional_fcl"]={str(r+1):dict(name=name, fcl_percent=float(percentages[r]) if np.isfinite(percentages[r]) else None)
                           for r,name in enumerate(roi_names)}

