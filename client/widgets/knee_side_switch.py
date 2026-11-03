"""Compact, keyboard-accessible left/right knee switch."""
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen


class KneeSideSwitch(QtWidgets.QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(False)  # Left knee by default; checked means right.
        self.setFixedSize(112, 34)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.toggled.connect(self._refresh)
        self._refresh()

    def currentData(self):
        return "right" if self.isChecked() else "left"

    def _refresh(self):
        side = "右膝" if self.isChecked() else "左膝"
        self.setAccessibleName(f"膝关节侧别：{side}")
        self.setToolTip(f"当前：{side}；点击或按空格切换左右膝")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(1.0 if self.isEnabled() else .45)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f59e42"))
        painter.drawRoundedRect(QRectF(1, 1, 110, 32), 16, 16)
        right = self.isChecked()
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(81 if right else 5, 5, 24, 24))
        painter.setPen(QColor("#202226"))
        painter.drawText(QRectF(12 if right else 35, 0, 65, 34), Qt.AlignCenter,
                         "右膝" if right else "左膝")
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#e8eaed"), 1, Qt.DotLine))
            painter.drawRoundedRect(QRectF(2, 2, 108, 30), 15, 15)
