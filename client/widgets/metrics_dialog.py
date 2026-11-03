from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QSize, QPoint, pyqtSignal

class MetricsDialog(QtWidgets.QDialog):
    def __init__(self, metrics, parent=None):
        super().__init__(parent)
        self.setWindowTitle("形态学指标（覆盖面积为 cAB）")
        self.resize(850, 620)
        layout = QtWidgets.QVBoxLayout(self)
        regions = metrics.get("regions", {})
        table = QtWidgets.QTableWidget(len(regions), 5)
        table.setAlternatingRowColors(True)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #292c31;
                alternate-background-color: #34383e;
                color: #e8eaed;
                gridline-color: #41464e;
                selection-background-color: #f59e42;
                selection-color: #202226;
            }
        """)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setHorizontalHeaderLabels(["区域", "FCL (%)", "平均厚度 (mm)", "覆盖面积 (mm²)", "体积 (mm³)"])
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        for row, (region, values) in enumerate(regions.items()):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(region))
            for col, key in enumerate(("FCL", "Mean Thickness", "Surface Area", "Volume"), 1):
                value = values.get(key)
                table.setItem(row, col, QtWidgets.QTableWidgetItem("不可计算" if value is None else f"{value:.4f}"))
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        layout.addWidget(table)
        layout.addWidget(QtWidgets.QLabel("缺损区域的零厚度参与平均；灰色骨面不表示健康判断。"))
