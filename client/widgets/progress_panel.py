from PyQt5 import QtWidgets

class ProgressPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.pipeline_label = QtWidgets.QLabel("就绪，请打开 MRI")
        self.pipeline_label.setMinimumWidth(0)
        self.pipeline_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.pipeline_bar = QtWidgets.QProgressBar()
        self.pipeline_bar.setRange(0, 5)
        self.pipeline_bar.setValue(0)
        self.pipeline_bar.setFixedWidth(220)
        self.pipeline_bar.setFixedHeight(12)
        self.pipeline_bar.setTextVisible(False)
        self.pipeline_bar.setToolTip("阶段进度，不代表耗时百分比")
        self.pipeline_bar.hide()
        self.elapsed_label = QtWidgets.QLabel("")
        layout.addWidget(self.pipeline_label, 1)
        layout.addWidget(self.pipeline_bar)
        layout.addWidget(self.elapsed_label)
