from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QSize, QPoint, pyqtSignal

import vtkmodules.all as vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

class ViewGrid(QtWidgets.QWidget):
    slice_changed = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        grid = QtWidgets.QGridLayout()
        layout.addLayout(grid, 1)
        self.widgets = {}
        self.renderers = {}
        self.slice_sliders = {}
        self.slice_labels = {}
        for key, title, row, col in (
            ("3d", "三维模型 / 软骨覆盖区域", 0, 0),
            ("z", "Z 方向切片", 0, 1),
            ("x", "X 方向切片", 1, 0),
            ("y", "Y 方向切片", 1, 1),
        ):
            panel = QtWidgets.QGroupBox(title)
            box = QtWidgets.QVBoxLayout(panel)
            widget = QVTKRenderWindowInteractor(panel)
            view_row = QtWidgets.QHBoxLayout()
            view_row.addWidget(widget, 1)
            box.addLayout(view_row, 1)
            if key != "3d":
                slice_row = QtWidgets.QVBoxLayout()
                slider = QtWidgets.QSlider(Qt.Vertical)
                slider.setFixedWidth(22)
                slider.setStyleSheet("""
                    QSlider::groove:vertical { width: 4px; background: #41464e; border-radius: 2px; }
                    QSlider::handle:vertical { height: 16px; margin: 0 -5px;
                        background: #f59e42; border-radius: 7px; }
                    QSlider::handle:vertical:disabled { background: #646a73; }
                """)
                slider.setRange(0, 0)
                slider.setEnabled(False)
                slider.setSingleStep(1)
                slider.setToolTip("拖动浏览切片；方向键逐层移动")
                label = QtWidgets.QLabel("未加载")
                label.setAlignment(Qt.AlignCenter)
                slice_row.addWidget(slider, 1, Qt.AlignHCenter)
                slice_row.addWidget(label)
                view_row.addLayout(slice_row)
                self.slice_sliders[key] = slider
                self.slice_labels[key] = label
                slider.valueChanged.connect(lambda value, axis=key: self.slice_changed.emit(axis, value))
            renderer = vtk.vtkRenderer()
            renderer.SetBackground(.1, .1, .1)
            widget.GetRenderWindow().AddRenderer(renderer)
            if key == "3d":
                widget.GetRenderWindow().SetAlphaBitPlanes(1)
                widget.GetRenderWindow().SetMultiSamples(0)
                renderer.SetUseDepthPeeling(True)
                renderer.SetMaximumNumberOfPeels(100)
                renderer.SetOcclusionRatio(.1)
            style = vtk.vtkInteractorStyleTrackballCamera() if key == "3d" else vtk.vtkInteractorStyleImage()
            widget.GetRenderWindow().GetInteractor().SetInteractorStyle(style)
            self.widgets[key], self.renderers[key] = widget, renderer
            grid.addWidget(panel, row, col)
        self.vtk_widget = self.widgets["3d"]
        self.ren_3d = self.renderers["3d"]
