"""Two independent VTK dialogs sharing one physical thickness scale."""
import json
from pathlib import Path
import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QTimer
import vtkmodules.all as vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.util.numpy_support import vtk_to_numpy, numpy_to_vtk

def read_mesh(path, bone_label):
    reader = vtk.vtkXMLPolyDataReader()
    if not Path(path).is_file(): raise ValueError(f"厚度文件不存在：{path}")
    reader.SetFileName(str(path)); reader.Update()
    poly = vtk.vtkPolyData(); poly.DeepCopy(reader.GetOutput())
    n = poly.GetNumberOfCells()
    if reader.GetErrorCode() or not n or poly.GetNumberOfPolys() != n:
        raise ValueError("厚度模型为空或不是表面面片")
    arrays = {}
    for name in ("coverage_class","bone_label","thickness_mm","thickness_valid"):
        arr = poly.GetCellData().GetArray(name)
        if arr is None or arr.GetNumberOfComponents()!=1 or arr.GetNumberOfTuples()!=n:
            raise ValueError(f"缺少或无效的面片属性：{name}")
        arrays[name] = vtk_to_numpy(arr).copy()
    c,t,valid = arrays["coverage_class"],arrays["thickness_mm"],arrays["thickness_valid"]
    if not np.isin(c,[0,1,2]).all() or not np.isin(valid,[0,1]).all() or not (arrays["bone_label"]==bone_label).all():
        raise ValueError("厚度模型分类或骨标签无效")
    if not np.isfinite(vtk_to_numpy(poly.GetPoints().GetData())).all():
        raise ValueError("模型坐标无效")
    if np.any((valid==1) & (~np.isfinite(t) | (t<0))):
        raise ValueError("有效厚度包含非法数值")
    optional = ("roi_id","fcl_percent","fcl_valid","roi_candidate_count")
    present = [poly.GetCellData().GetArray(name) is not None for name in optional]
    if any(present) and not all(present): raise ValueError("FCL 属性不完整")
    if all(present):
        for name in optional:
            arr=poly.GetCellData().GetArray(name)
            if arr.GetNumberOfComponents()!=1 or arr.GetNumberOfTuples()!=n:
                raise ValueError("FCL 属性数量错误")
            arrays[name]=vtk_to_numpy(arr).copy()
        f=arrays["fcl_percent"];fv=arrays["fcl_valid"]
        if not np.isin(fv,[0,1]).all() or np.any((fv==1)&(~np.isfinite(f)|(f<0)|(f>100))):
            raise ValueError("FCL 百分比无效")
        if not np.isin(arrays["roi_id"],range(21)).all(): raise ValueError("分区编号无效")
    return poly,arrays

def thickness_rgb(fraction):
    """Thin blue -> cyan -> yellow -> orange -> thick red; shared with legend."""
    x = np.clip(np.asarray(fraction, dtype=float), 0, 1)
    stops = np.array([[30, 65, 210], [35, 205, 220], [250, 225, 60],
                      [250, 140, 30], [230, 45, 40]], dtype=float)
    anchors = np.linspace(0, 1, len(stops))
    rgb = np.stack([np.interp(x, anchors, stops[:, channel])
                    for channel in range(3)], axis=-1)
    return np.rint(rgb).astype(np.uint8)

def colors_for(arrays, maximum):
    c,t,valid = arrays["coverage_class"],arrays["thickness_mm"],arrays["thickness_valid"]
    colors = np.tile(np.array([180,180,180],np.uint8),(len(c),1))
    colors[c==2] = [0,0,0]
    colors[(c==1)&(valid==0)] = [170,70,210]
    ok = (c==1)&(valid==1)
    colors[ok] = thickness_rgb(t[ok]/maximum)
    return colors

class ThicknessWindow(QtWidgets.QDialog):
    def __init__(self, name, poly, arrays, manager, parent):
        super().__init__(parent, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self._disposed = False
        self.name,self.poly,self.arrays,self.manager = name,poly,arrays,manager
        self.setWindowTitle(("股骨" if name=="femur" else "胫骨")+"软骨厚度")
        self.resize(650,650)
        layout=QtWidgets.QVBoxLayout(self)
        row=QtWidgets.QHBoxLayout()
        self.mode=QtWidgets.QComboBox()
        self.mode.addItem("软骨厚度","thickness")
        self.mode.addItem("分区 FCL","fcl")
        self.mode.model().item(1).setEnabled(manager.fcl_available)
        self.mode.setToolTip("旧结果需重新计算，才有分区 FCL 数据")
        self.mode.currentIndexChanged.connect(lambda _: manager.set_mode(self.mode.currentData()))
        row.addWidget(self.mode)
        self.scale_label=QtWidgets.QLabel("统一色标上限 (mm)")
        row.addWidget(self.scale_label)
        self.maximum=QtWidgets.QDoubleSpinBox();self.maximum.setRange(.1,1000);self.maximum.setDecimals(2)
        self.maximum.setValue(manager.maximum);row.addWidget(self.maximum)
        reset=QtWidgets.QPushButton("恢复关节面视角");row.addWidget(reset)
        layout.addLayout(row)
        note=QtWidgets.QLabel("薄：蓝 → 青 → 黄 → 橙 → 红：厚　黑：估计全层缺损　灰：未评估　紫：厚度无效")
        note.setWordWrap(True);layout.addWidget(note)
        self.note=note
        self.thickness_note=note.text()
        self.roi_values=QtWidgets.QComboBox()
        self.roi_values.setToolTip("报告中的分区 FCL 数值；不改变原始指标")
        for key, entry in manager.regional_fcl.items():
            rid=int(key)
            if (name=="femur" and rid<=10) or (name=="tibia" and rid>10):
                value=entry.get("fcl_percent")
                self.roi_values.addItem(entry["name"]+"："+("不可计算" if value is None else f"{value:.2f}%"))
        self.roi_values.hide()
        layout.addWidget(self.roi_values)
        layout.addWidget(QtWidgets.QLabel("可拖动旋转；默认视角按两骨相对位置估计，可手动调整"))
        self.widget=QVTKRenderWindowInteractor(self);layout.addWidget(self.widget,1)
        self.renderer=vtk.vtkRenderer();self.renderer.SetBackground(.12,.12,.12)
        self.widget.GetRenderWindow().AddRenderer(self.renderer)
        self.widget.GetRenderWindow().GetInteractor().SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        mapper=vtk.vtkPolyDataMapper();mapper.SetInputData(poly)
        mapper.SetScalarModeToUseCellFieldData();mapper.SelectColorArray("heat_rgb")
        mapper.SetColorModeToDirectScalars()
        actor=vtk.vtkActor();actor.SetMapper(mapper)
        actor.GetProperty().LightingOff()
        self.renderer.AddActor(actor)
        self.lut=vtk.vtkLookupTable();self.lut.SetNumberOfTableValues(256)
        self.bar=vtk.vtkScalarBarActor();self.bar.SetLookupTable(self.lut);self.bar.SetTitle("Thickness (mm)")
        self.bar.SetNumberOfLabels(5);self.bar.SetWidth(.12);self.bar.SetHeight(.65)
        self.renderer.AddViewProp(self.bar)
        axes=vtk.vtkAxesActor();axes.SetXAxisLabelText("R");axes.SetYAxisLabelText("A");axes.SetZAxisLabelText("S")
        self.orientation=vtk.vtkOrientationMarkerWidget()
        self.orientation.SetOrientationMarker(axes)
        self.orientation.SetInteractor(self.widget.GetRenderWindow().GetInteractor())
        self.orientation.SetViewport(0,0,.22,.22)
        self.initialized=False
        self.maximum.valueChanged.connect(manager.set_maximum)
        reset.clicked.connect(self.reset_view)
        self.update_colors(manager.maximum, render=False)
        self.reset_view(render=False)

    def update_colors(self, maximum, render=True):
        self.maximum.blockSignals(True);self.maximum.setValue(maximum);self.maximum.blockSignals(False)
        is_fcl=self.manager.mode=="fcl"
        self.mode.blockSignals(True);self.mode.setCurrentIndex(1 if is_fcl else 0);self.mode.blockSignals(False)
        self.maximum.setEnabled(not is_fcl)
        self.scale_label.setText("固定色标上限 (%)" if is_fcl else "统一色标上限 (mm)")
        self.bar.SetTitle("Regional FCL (%)" if is_fcl else "Thickness (mm)")
        self.setWindowTitle(("股骨" if self.name=="femur" else "胫骨")+("分区 FCL" if is_fcl else "软骨厚度"))
        self.note.setText("蓝 → 红：分区 FCL 低 → 高（0–100%）；灰：未评估；紫：无效。每区同色，不是局部厚度。" if is_fcl else self.thickness_note)
        self.roi_values.setVisible(is_fcl)
        if is_fcl:
            c=self.arrays["coverage_class"];valid=self.arrays["fcl_valid"]
            colors=np.tile(np.array([180,180,180],np.uint8),(len(c),1))
            colors[(c!=0)&(valid==0)]=[170,70,210]
            ok=(c!=0)&(valid==1)
            colors[ok]=thickness_rgb(self.arrays["fcl_percent"][ok]/100.)
        else:
            colors=colors_for(self.arrays,maximum)
        rgb=numpy_to_vtk(colors,deep=True);rgb.SetName("heat_rgb")
        self.poly.GetCellData().RemoveArray("heat_rgb");self.poly.GetCellData().AddArray(rgb);self.poly.Modified()
        self.lut.SetTableRange(0,maximum);self.lut.Build()
        for i in range(256):
            x=i/255
            color=thickness_rgb(x)/255
            self.lut.SetTableValue(i,*color,1)
        if render and self.initialized and self.isVisible() and not self._disposed:self.widget.GetRenderWindow().Render()

    def reset_view(self, checked=False, render=True):
        target=self.manager.centers[self.name]
        other=self.manager.centers["tibia" if self.name=="femur" else "femur"]
        direction=other-target
        if np.linalg.norm(direction)<1e-6: direction=np.array([0,0,-1 if self.name=="femur" else 1.])
        direction=direction/np.linalg.norm(direction)
        up=np.array([0.,1.,0.]);up-=np.dot(up,direction)*direction
        if np.linalg.norm(up)<1e-6: up=np.array([1.,0.,0.])
        camera=self.renderer.GetActiveCamera()
        camera.SetFocalPoint(*target);camera.SetPosition(*(target+direction*300));camera.SetViewUp(*up)
        camera.ParallelProjectionOn()
        self.renderer.ResetCamera();self.renderer.ResetCameraClippingRange()
        if render and self.initialized and self.isVisible() and not self._disposed:self.widget.GetRenderWindow().Render()

    def closeEvent(self, event):
        # Closing a viewer is not disposal: retain VTK context and camera.
        event.ignore()
        self.hide()

    def reject(self):
        # Escape follows the same hide-only path.
        self.hide()

    def showEvent(self,event):
        super().showEvent(event)
        QTimer.singleShot(0, self._render_after_show)

    def _render_after_show(self):
        if self._disposed or not self.isVisible():
            return
        if not self.initialized:
            self.widget.Initialize()
            self.orientation.SetEnabled(1)
            self.orientation.InteractiveOff()
            self.initialized=True
        self.widget.GetRenderWindow().Render()

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self.hide()
        if self.initialized:
            self.orientation.SetEnabled(0)
        self.orientation.SetInteractor(None)
        self.widget.Finalize()
        self.initialized = False
        self.deleteLater()

class ThicknessViews:
    def __init__(self,parent):
        self.parent=parent;self.windows={};self.maximum=5.;self.centers={}
        self.mode="thickness";self.fcl_available=False;self.regional_fcl={}
    def clear(self):
        for window in self.windows.values():window.dispose()
        self.windows={}
    def load(self,files):
        meta=json.loads(Path(files["thickness_manifest"]).read_text(encoding="utf-8-sig"))
        if meta.get("coordinate_system")!="NIfTI RAS" or meta.get("units")!="mm" or meta.get("association")!="CellData":
            raise ValueError("厚度模型坐标或属性约定不兼容")
        meshes={name:read_mesh(files[name+"_thickness"],label) for name,label in (("femur",1),("tibia",3))}
        self.clear()
        self.mode="thickness"
        self.fcl_available=all("fcl_percent" in arrays for _,arrays in meshes.values())
        self.regional_fcl=meta.get("regional_fcl",{})
        for name,(poly,arrays) in meshes.items():
            value=meta.get("bones",{}).get(name,{}).get("assessed_center_ras_mm")
            center=np.asarray(value,dtype=float) if value is not None else np.asarray(poly.GetCenter())
            if center.shape!=(3,) or not np.isfinite(center).all():center=np.asarray(poly.GetCenter())
            self.centers[name]=center
        # Fixed 5 mm default supports comparisons; both views can change it together.
        try:
            for name,(poly,arrays) in meshes.items():
                self.windows[name]=ThicknessWindow(name,poly,arrays,self,self.parent)
        except Exception:
            self.clear();raise
    def set_mode(self,mode):
        if mode=="fcl" and not self.fcl_available: return
        self.mode=mode
        for window in self.windows.values():
            window.update_colors(100. if mode=="fcl" else self.maximum)

    def set_maximum(self,value):
        if self.mode=="fcl": return
        self.maximum=max(.1,float(value))
        for window in self.windows.values():window.update_colors(self.maximum)
    def show(self):
        if not self.windows:
            return
        screen=self.parent.screen().availableGeometry()
        width=min(650,screen.width()//2)
        height=min(650,screen.height())
        for i,window in enumerate(self.windows.values()):
            # Position hidden windows before showing, avoiding immediate
            # resize/recreation of a just-rendered native OpenGL window.
            if not window.isVisible():
                window.resize(width,height)
                window.move(screen.left()+i*width,screen.top())
            window.showNormal()
            window.raise_()
            window.activateWindow()
