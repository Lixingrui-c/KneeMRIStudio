"""NIfTI reference-grid loading and display meshes (not morphometry meshes)."""
from dataclasses import dataclass
import numpy as np
import nibabel as nib
from nibabel.processing import resample_from_to
import vtkmodules.all as vtk
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy


@dataclass
class Volume:
    image: object
    affine: np.ndarray
    shape: tuple
    spacing: np.ndarray


def load_volume(path, reference=None, labels=False):
    source = nib.load(str(path))
    if len(source.shape) != 3:
        raise ValueError("需要三维 NIfTI 文件")
    if not np.all(np.isfinite(source.affine)) or abs(np.linalg.det(source.affine[:3, :3])) < 1e-12:
        raise ValueError("NIfTI 空间变换无效")
    if reference is None:
        source = nib.as_closest_canonical(source)
    elif source.shape != reference.shape or not np.allclose(source.affine, reference.affine, atol=1e-4):
        source = resample_from_to(source, (reference.shape, reference.affine), order=0 if labels else 1)
    data = np.asarray(source.dataobj)
    if not np.all(np.isfinite(data)):
        raise ValueError("图像包含非有限数值")
    if labels and (not np.allclose(data, np.rint(data)) or not np.isin(data, range(6)).all()):
        raise ValueError("分割标签必须为 0～5 的整数")
    data = data.astype(np.uint8 if labels else np.float32)
    spacing = np.linalg.norm(source.affine[:3, :3], axis=0)
    image = vtk.vtkImageData()
    image.SetDimensions(*data.shape)
    image.SetSpacing(*spacing)
    image.SetOrigin(0, 0, 0)
    image.GetPointData().SetScalars(numpy_to_vtk(data.ravel(order="F"), deep=True))
    return Volume(image, source.affine.copy(), data.shape, spacing)


def world_matrix(volume):
    # vtk image already includes spacing; apply only direction/shear + translation.
    affine = volume.affine.copy()
    affine[:3, :3] /= volume.spacing[None, :]
    matrix = vtk.vtkMatrix4x4()
    for i in range(4):
        for j in range(4):
            matrix.SetElement(i, j, float(affine[i, j]))
    return matrix


def create_surface_actors(volume, labels=range(1, 6)):
    """Return label -> Actor. Exact 0.5 boundary, no geometry smoothing."""
    actors = {}
    colors = [(0.9, .2, .2), (.2, .9, .2), (.2, .35, .95), (.9, .9, .2), (.9, .5, .1)]
    for label in labels:
        threshold = vtk.vtkImageThreshold()
        threshold.SetInputData(volume.image)
        threshold.ThresholdBetween(label, label)
        threshold.SetInValue(1)
        threshold.SetOutValue(0)
        threshold.SetOutputScalarTypeToUnsignedChar()
        pad = vtk.vtkImageConstantPad()
        pad.SetInputConnection(threshold.GetOutputPort())
        e = volume.image.GetExtent()
        pad.SetOutputWholeExtent(e[0]-1, e[1]+1, e[2]-1, e[3]+1, e[4]-1, e[5]+1)
        pad.SetConstant(0)
        mc = vtk.vtkMarchingCubes()
        mc.SetInputConnection(pad.GetOutputPort())
        mc.SetValue(0, .5)
        mc.ComputeNormalsOn()
        mc.Update()
        if mc.GetOutput().GetNumberOfPoints() == 0:
            continue
        poly = vtk.vtkPolyData()
        poly.DeepCopy(mc.GetOutput())
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)
        mapper.ScalarVisibilityOff()
        mapper.SetResolveCoincidentTopologyToPolygonOffset()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetUserMatrix(world_matrix(volume))
        prop = actor.GetProperty()
        prop.SetColor(*colors[label-1])
        prop.SetOpacity(.7)
        actors[label] = actor
    return actors


def create_template_cartilage_actors(volume):
    """Display-only template cartilage in patient world coordinates."""
    actors = create_surface_actors(volume, labels=(2, 4, 5))
    for actor in actors.values():
        actor.GetProperty().SetColor(.8, .25, 1.)
        actor.GetProperty().SetOpacity(.35)
    return actors


def load_coverage_actors(path):
    """Read world-RAS metric geometry. No affine, smoothing or marching cubes."""
    from pathlib import Path
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(str(path))
    reader.Update()
    poly = reader.GetOutput()
    n = poly.GetNumberOfCells()
    if reader.GetErrorCode() or n == 0 or poly.GetNumberOfPoints() == 0:
        raise ValueError("分析网格为空或 VTP 无法读取")
    if poly.GetNumberOfPolys() != n:
        raise ValueError("分析网格必须只包含表面面片")
    arrays = {}
    for name, allowed in (("coverage_class", [0, 1, 2]), ("bone_label", [1, 3])):
        array = poly.GetCellData().GetArray(name)
        if array is None or array.GetNumberOfComponents() != 1 or array.GetNumberOfTuples() != n:
            raise ValueError(f"VTP 缺少有效的面片属性：{name}")
        values = vtk_to_numpy(array)
        if not np.isin(values, allowed).all():
            raise ValueError(f"VTP 属性 {name} 包含未知分类")
        arrays[name] = values
    if not np.isfinite(vtk_to_numpy(poly.GetPoints().GetData())).all():
        raise ValueError("分析网格坐标无效")
    # Deterministic colors from categorical CELL labels; no interpolated point labels.
    rgb = np.array([[180,180,180], [45,190,80], [230,50,50]], dtype=np.uint8)[arrays["coverage_class"].astype(int)]
    colors = numpy_to_vtk(rgb, deep=True)
    colors.SetName("coverage_rgb")
    poly.GetCellData().AddArray(colors)
    actors = {}
    for label in (1, 3):
        ids = np.flatnonzero(arrays["bone_label"] == label)
        if not len(ids):
            continue
        cell_ids = vtk.vtkIdList()
        for i in ids:
            cell_ids.InsertNextId(int(i))
        extract = vtk.vtkExtractCells()
        extract.SetInputData(poly)
        extract.SetCellList(cell_ids)
        geometry = vtk.vtkGeometryFilter()
        geometry.SetInputConnection(extract.GetOutputPort())
        geometry.Update()
        surface = vtk.vtkPolyData()
        surface.DeepCopy(geometry.GetOutput())
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(surface)
        mapper.SetScalarModeToUseCellFieldData()
        mapper.SelectColorArray("coverage_rgb")
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetOpacity(1.0)
        actor.GetProperty().SetAmbient(.35)
        actor.GetProperty().SetDiffuse(.65)
        actors[label] = actor
    return actors


def create_slice_actors(volume):
    """Reference-grid central slices; oblique acquisitions remain grid-aligned."""
    center = (np.asarray(volume.shape) // 2) * volume.spacing
    directions = {
        "x": (0, 1, 0, 0, 0, 1, 1, 0, 0),
        "y": (1, 0, 0, 0, 0, 1, 0, 1, 0),
        "z": (1, 0, 0, 0, 1, 0, 0, 0, 1),
    }
    

    values = vtk_to_numpy(
        volume.image.GetPointData().GetScalars()
    )

    # 排除常见的零背景，以组织灰度估计显示范围
    valid = values[np.isfinite(values) & (values > 0)]

    if valid.size:
        lo, hi = np.percentile(valid, [1, 99])
    else:
        lo, hi = volume.image.GetScalarRange()

    window = max(float(hi - lo), 1.0)
    level = float((lo + hi) / 2)
    actors = {}
    for axis, direction in directions.items():
        reslice = vtk.vtkImageReslice()
        reslice.SetInputData(volume.image)
        reslice.SetOutputDimensionality(2)
        reslice.SetResliceAxesDirectionCosines(*direction)
        reslice.SetResliceAxesOrigin(*center)
        reslice.SetInterpolationModeToLinear()
        # Fix in-plane geometry so moving through slices does not move the image.
        reslice.Update()
        grid = reslice.GetOutput()
        origin, spacing, extent = grid.GetOrigin(), grid.GetSpacing(), grid.GetExtent()
        reslice.SetOutputOrigin(*origin)
        reslice.SetOutputSpacing(*spacing)
        reslice.SetOutputExtent(*extent)
        mapper = vtk.vtkImageSliceMapper()
        mapper.SetInputConnection(reslice.GetOutputPort())
        actor = vtk.vtkImageSlice()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColorWindow(window)
        actor.GetProperty().SetColorLevel(level)
        actor._reslice = reslice
        actors[axis] = actor
    return actors


def create_template_overlays(volume, base_actors):
    return create_cartilage_overlays(volume, base_actors, (.8, .25, 1.), 1)


def create_patient_overlays(volume, base_actors):
    return create_cartilage_overlays(volume, base_actors, (.15, .9, .35), 2)


def create_cartilage_overlays(volume, base_actors, color, layer):
    """Template labels must already be resampled onto the MRI reference grid."""
    lut = vtk.vtkLookupTable()
    lut.SetNumberOfTableValues(6)
    lut.SetTableRange(0, 5)
    lut.Build()
    for label in range(6):
        lut.SetTableValue(label, *color, 1. if label in (2, 4, 5) else 0.)
    overlays = {}
    for axis, base in base_actors.items():
        reference = base._reslice
        reference.Update()
        grid = reference.GetOutput()
        reslice = vtk.vtkImageReslice()
        reslice.SetInputData(volume.image)
        reslice.SetOutputDimensionality(2)
        reslice.SetResliceAxes(reference.GetResliceAxes())
        reslice.SetOutputOrigin(*grid.GetOrigin())
        reslice.SetOutputSpacing(*grid.GetSpacing())
        reslice.SetOutputExtent(*grid.GetExtent())
        reslice.SetInterpolationModeToNearestNeighbor()
        colors = vtk.vtkImageMapToColors()
        colors.SetInputConnection(reslice.GetOutputPort())
        colors.SetLookupTable(lut)
        colors.SetOutputFormatToRGBA()
        mapper = vtk.vtkImageSliceMapper()
        mapper.SetInputConnection(colors.GetOutputPort())
        actor = vtk.vtkImageSlice()
        actor.SetMapper(mapper)
        actor.GetProperty().SetLayerNumber(layer)
        actor.GetProperty().SetInterpolationTypeToNearest()
        actor.GetProperty().SetOpacity(.4)
        actor._reslice = reslice
        overlays[axis] = actor
    return overlays


def set_slice_index(volume, axis, index, base_actor, overlay_actor=None):
    """Zero-based reference-grid slice; keep MRI and label reslices together."""
    dimension = {"x": 0, "y": 1, "z": 2}[axis]
    index = int(index)
    if not 0 <= index < volume.shape[dimension]:
        raise ValueError("切片序号超出影像范围")
    origin = list(base_actor._reslice.GetResliceAxesOrigin())
    origin[dimension] = index * float(volume.spacing[dimension])
    base_actor._reslice.SetResliceAxesOrigin(*origin)
    base_actor._reslice.Modified()
    if overlay_actor is not None:
        overlay_actor._reslice.SetResliceAxes(base_actor._reslice.GetResliceAxes())
        overlay_actor._reslice.Modified()
