from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt


class TaskProgressDialog(QtWidgets.QProgressDialog):
    """Stage progress; cancellation only stops local waiting."""
    def __init__(self, parent=None):
        super().__init__("", "停止等待", 0, 5, parent)
        self.setWindowTitle("MRI 处理任务")
        self.setWindowModality(Qt.NonModal)
        self.setMinimumWidth(460)
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
