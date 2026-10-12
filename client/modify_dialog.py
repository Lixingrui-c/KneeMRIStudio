import PyQt5.QtWidgets as QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal

class seg_modify_dialog(QtWidgets.QDialog):
    """ 分割部件和不透明度修改对话框 """

    #点击应用后，向主窗口传递两个列表，分别是选择的标签和对应的不透明度
    setting_applied = pyqtSignal(list, list)

    LABEL_NAMES = (
        "股骨",
        "股骨软骨",
        "胫骨",
        "内侧胫骨软骨",
        "外侧胫骨软骨",
    )


    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("分割与显示设置")
        self.resize(440, 360)

        # 这些控件现在属于弹窗，不再放在主窗口里。
        self.choose_boxes = []
        self.opacity_sliders = []

        self._create_ui()
        self.reset_defaults()

    def _create_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        description = QtWidgets.QLabel(
            "选择需要显示的部件，并调整不透明度。\n"
            "修改后点击下方按钮应用到模型。"
        )
        description.setWordWrap(True)
        main_layout.addWidget(description)

        self.settings_group = QtWidgets.QGroupBox("显示设置")
        grid = QtWidgets.QGridLayout(self.settings_group)

        grid.addWidget(QtWidgets.QLabel("显示部件"), 0, 0)
        grid.addWidget(QtWidgets.QLabel("不透明度"), 0, 1)

        for row, name in enumerate(self.LABEL_NAMES, start=1):
            checkbox = QtWidgets.QCheckBox(name)

            slider = QtWidgets.QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setToolTip("0% 为完全透明，100% 为完全不透明")

            value_label = QtWidgets.QLabel()
            value_label.setMinimumWidth(40)
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # 默认参数保存本次循环的标签对象，
            # 确保每个滑块更新自己对应的数值标签。
            slider.valueChanged.connect(
                lambda value, label=value_label:
                    label.setText(f"{value}%")
            )

            # 未勾选的部件暂时不能调整不透明度。
            checkbox.toggled.connect(slider.setEnabled)
            checkbox.toggled.connect(value_label.setEnabled)

            self.choose_boxes.append(checkbox)
            self.opacity_sliders.append(slider)

            grid.addWidget(checkbox, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(value_label, row, 2)

        grid.setColumnStretch(1, 1)
        main_layout.addWidget(self.settings_group)

        button_layout = QtWidgets.QHBoxLayout()

        self.reset_button = QtWidgets.QPushButton("恢复默认")
        self.reset_button.clicked.connect(self.reset_defaults)

        self.apply_button = QtWidgets.QPushButton("分割并显示")
        self.apply_button.clicked.connect(self._emit_settings)

        self.close_button = QtWidgets.QPushButton("关闭")
        self.close_button.clicked.connect(self.close)

        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.close_button)

        main_layout.addLayout(button_layout)

    def set_settings(self, selected_labels, opacity_labels):
        """根据主窗口保存的设置，填充控件。"""
        count = len(self.LABEL_NAMES)

        if len(selected_labels) != count or len(opacity_labels) != count:
            raise ValueError(f"需要提供 {count} 个部件的显示设置")

        for index in range(count):
            self.choose_boxes[index].setChecked(
                bool(selected_labels[index])
            )
            self.opacity_sliders[index].setValue(
                int(opacity_labels[index])
            )

    def get_settings(self):
        """读取当前控件，返回两组新的列表。"""
        selected_labels = [
            checkbox.isChecked()
            for checkbox in self.choose_boxes
        ]

        opacity_labels = [
            slider.value()
            for slider in self.opacity_sliders
        ]

        return selected_labels, opacity_labels

    def reset_defaults(self):
        """只恢复弹窗中的设置，点击应用后才更新模型。"""
        count = len(self.LABEL_NAMES)
        self.set_settings(
            [True] * count,
            [70] * count,
        )

    def set_has_segmentation(self, has_segmentation):
        """根据是否已有分割结果，更新按钮文字。"""
        self.apply_button.setText(
            "应用显示" if has_segmentation else "分割并显示"
        )

    def set_busy(self, busy):
        """分割期间禁止再次提交或修改设置。"""
        self.settings_group.setEnabled(not busy)
        self.reset_button.setEnabled(not busy)
        self.apply_button.setEnabled(not busy)

    def _emit_settings(self):
        """发送设置，由主窗口决定如何处理。"""
        selected_labels, opacity_labels = self.get_settings()

        self.setting_applied.emit(
            selected_labels,
            opacity_labels,
        )