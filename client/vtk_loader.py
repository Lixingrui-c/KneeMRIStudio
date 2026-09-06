import os
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
import vtkmodules.all as vtk

def open_raw_nii_gz(file_path):
        
    reader = vtk.vtkNIFTIImageReader()
    reader.SetFileName(file_path)
    reader.Update()
    volume = reader.GetOutput()

    if volume is None:
        raise RuntimeError(
            "读取失败"
        )

    return volume


def create_slice_actors(raw_volume, slice_index=None):

    image = raw_volume
    extent = image.GetExtent()
    spacing = image.GetSpacing()
    origin = image.GetOrigin()

    if slice_index is None:
        slice_index = [
            (extent[0] + extent[1]) // 2,
            (extent[2] + extent[3]) // 2,
            (extent[4] + extent[5]) // 2
        ]

    actors = []

    # ---------------- AXIAL (Z) ----------------
    reslice_z = vtk.vtkImageReslice()
    reslice_z.SetInputData(image)
    reslice_z.SetOutputDimensionality(2)

    reslice_z.SetResliceAxesDirectionCosines(
        1,0,0,
        0,1,0,
        0,0,1
    )

    z = origin[2] + slice_index[2] * spacing[2]
    reslice_z.SetResliceAxesOrigin(origin[0], origin[1], z)

    mapper_z = vtk.vtkImageSliceMapper()
    mapper_z.SetInputConnection(reslice_z.GetOutputPort())

    actor_z = vtk.vtkImageSlice()
    actor_z.SetMapper(mapper_z)

    actors.append(actor_z)

    # ---------------- SAGITTAL (X) ----------------
    reslice_x = vtk.vtkImageReslice()
    reslice_x.SetInputData(image)
    reslice_x.SetOutputDimensionality(2)

    reslice_x.SetResliceAxesDirectionCosines(
        0,1,0,
        0,0,1,
        1,0,0
    )

    x = origin[0] + slice_index[0] * spacing[0]
    reslice_x.SetResliceAxesOrigin(x, origin[1], origin[2])

    mapper_x = vtk.vtkImageSliceMapper()
    mapper_x.SetInputConnection(reslice_x.GetOutputPort())

    actor_x = vtk.vtkImageSlice()
    actor_x.SetMapper(mapper_x)

    actors.append(actor_x)

    # ---------------- CORONAL (Y) ----------------
    reslice_y = vtk.vtkImageReslice()
    reslice_y.SetInputData(image)
    reslice_y.SetOutputDimensionality(2)

    reslice_y.SetResliceAxesDirectionCosines(
        1,0,0,
        0,0,1,
        0,1,0
    )

    y = origin[1] + slice_index[1] * spacing[1]
    reslice_y.SetResliceAxesOrigin(origin[0], y, origin[2])

    mapper_y = vtk.vtkImageSliceMapper()
    mapper_y.SetInputConnection(reslice_y.GetOutputPort())

    actor_y = vtk.vtkImageSlice()
    actor_y.SetMapper(mapper_y)

    actors.append(actor_y)

    return actors


def create_surface_actors(image_data, contour_values ,Opacity):
    """
    使用 Marching Cubes 从体积数据中提取等值面,包括1,2,3,4,5,对应不同的膝关节区域
    并进行平滑、计算法线,返回5个 vtkActor
    """

    if image_data is None:
        return

    ##设置颜色
    colors = [
        (0.9, 0.2, 0.2), 
        (0.2, 0.9, 0.2), 
        (0.2, 0.2, 0.9), 
        (0.9, 0.9, 0.2), 
        (0.9, 0.5, 0.1)
    ]

    actors = []
    something_wrong = False
    #1.提取表面
    for idx,val in enumerate(contour_values):

        if val==1: # val标识该部分是否被选中

            threshold = vtk.vtkImageThreshold()
            threshold.SetInputData(image_data)
            threshold.ThresholdBetween(idx+1, idx+1.5)   # 保留区间内的值
            threshold.SetInValue(1.0)               # 区间内设为1
            threshold.SetOutValue(0.0)              # 区间外设为0
            threshold.Update()

            marching_cubes = vtk.vtkMarchingCubes()
            marching_cubes.SetInputConnection(threshold.GetOutputPort())
            marching_cubes.SetValue(0, 0.7)   
            marching_cubes.Update()
            
            if marching_cubes.GetOutput().GetNumberOfPoints() == 0:
                something_wrong = True
                continue

            # 2. 平滑表面
            smoother = vtk.vtkWindowedSincPolyDataFilter()
            smoother.SetInputConnection(marching_cubes.GetOutputPort())
            smoother.SetNumberOfIterations(15)
            smoother.BoundarySmoothingOff()
            smoother.FeatureEdgeSmoothingOff()
            smoother.SetPassBand(0.1)
            smoother.Update()

            # 3. 计算法线
            normals = vtk.vtkPolyDataNormals()
            normals.SetInputConnection(smoother.GetOutputPort())
            normals.SetFeatureAngle(60.0)
            normals.Update()

            # 4. 映射器
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(normals.GetOutputPort())
            mapper.ScalarVisibilityOff()

            # 5. Actor
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)

            
            color = colors[idx % len(contour_values)]
            actor.GetProperty().SetColor(color)
            actor.GetProperty().SetSpecular(0.6)
            actor.GetProperty().SetSpecularPower(30)
            actor.GetProperty().SetOpacity(Opacity[idx]/100)
            actor.GetProperty().SetAmbient(0.2)
            actor.GetProperty().SetDiffuse(0.8)

            actors.append(actor)  

    if something_wrong:
        return None
    return actors