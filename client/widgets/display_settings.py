from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QSize, QPoint, pyqtSignal

class DisplaySettingsPopup(QtWidgets.QFrame):
    """Popup outside the main layout; Qt closes it on Escape/outside click."""
    def __init__(self, parent, toggle):
        super().__init__(parent, Qt.Popup)
        self.setAttribute(Qt.WA_NoMouseReplay, True)
        self.toggle = toggle
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet("DisplaySettingsPopup { background: #292c31; border: 1px solid #41464e; }")

    def hideEvent(self, event):
        self.toggle.blockSignals(True)
        self.toggle.setChecked(False)
        self.toggle.setArrowType(Qt.RightArrow)
        self.toggle.blockSignals(False)
        super().hideEvent(event)


class DisplaySettingsWidget(QtWidgets.QWidget):
    surface_changed = pyqtSignal()
    template_changed = pyqtSignal()
    patient_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.coverage_check = QtWidgets.QCheckBox("显示软骨覆盖区域")
        self.coverage_check.setToolTip("绿色表示软骨覆盖，灰色合并原灰色与红色区域；关闭后恢复普通分割模型")
        self.coverage_check.setChecked(True)
        self.display_settings_toggle = QtWidgets.QToolButton()
        self.display_settings_toggle.setText("显示与叠加设置（4 项）")
        self.display_settings_toggle.setCheckable(True)
        self.display_settings_toggle.setChecked(False)
        self.display_settings_toggle.setArrowType(Qt.RightArrow)
        self.display_settings_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.display_settings_toggle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.display_settings_toggle.setToolTip("展开或收起显示设置；不会关闭已启用的叠加")
        layout.addWidget(self.display_settings_toggle, 0, Qt.AlignLeft)
        self.display_settings_panel = DisplaySettingsPopup(self, self.display_settings_toggle)
        self.display_settings_panel.setFrameShape(QtWidgets.QFrame.StyledPanel)
        settings_layout = QtWidgets.QVBoxLayout(self.display_settings_panel)
        settings_layout.setContentsMargins(12, 6, 12, 6)
        self.display_settings_panel.hide()
        self.display_settings_toggle.toggled.connect(self.toggle_display_settings)
        coverage_controls = QtWidgets.QHBoxLayout()
        coverage_controls.addWidget(self.coverage_check)
        self.coverage_check.toggled.connect(self.surface_changed.emit)
        self.legend = QtWidgets.QLabel(
            '<span style="color:#2dbe50">■ 软骨覆盖</span>　'
            '<span style="color:#888">■ 其余骨面</span>')
        coverage_controls.addWidget(self.legend)
        self.legend.setWordWrap(False)
        self.legend.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        legend_policy = self.legend.sizePolicy()
        legend_policy.setRetainSizeWhenHidden(True)
        self.legend.setSizePolicy(legend_policy)
        coverage_controls.addStretch()
        settings_layout.addLayout(coverage_controls)
        overlay_controls = QtWidgets.QHBoxLayout()
        self.template_check = QtWidgets.QCheckBox("MRI 叠加模板软骨参考")
        self.template_check.setChecked(True)
        self.template_check.toggled.connect(self.template_changed.emit)
        overlay_controls.addWidget(self.template_check)
        overlay_controls.addWidget(QtWidgets.QLabel("不透明度"))
        self.template_opacity = QtWidgets.QSlider(Qt.Horizontal)
        self.template_opacity.setRange(0, 100)
        self.template_opacity.setValue(40)
        self.template_opacity.setMaximumWidth(180)
        self.template_opacity.valueChanged.connect(self.template_changed.emit)
        overlay_controls.addWidget(self.template_opacity)
        self.template_opacity_text = QtWidgets.QLabel("40%")
        overlay_controls.addWidget(self.template_opacity_text)
        overlay_controls.addWidget(QtWidgets.QLabel('<span style="color:#cc40ff">■ 模板软骨参考</span>（非厚度差值）'))
        overlay_controls.addStretch()
        settings_layout.addLayout(overlay_controls)
        patient_controls = QtWidgets.QHBoxLayout()
        self.patient_check = QtWidgets.QCheckBox("MRI 叠加患者软骨分割")
        self.patient_check.setChecked(True)
        patient_controls.addWidget(self.patient_check)
        patient_controls.addWidget(QtWidgets.QLabel("不透明度"))
        self.patient_opacity = QtWidgets.QSlider(Qt.Horizontal)
        self.patient_opacity.setRange(0, 100)
        self.patient_opacity.setValue(40)
        self.patient_opacity.setMaximumWidth(180)
        patient_controls.addWidget(self.patient_opacity)
        self.patient_opacity_text = QtWidgets.QLabel("40%")
        patient_controls.addWidget(self.patient_opacity_text)
        patient_controls.addWidget(QtWidgets.QLabel('<span style="color:#26e659">■ 患者软骨分割</span>（与紫色模板可分别开关）'))
        patient_controls.addStretch()
        self.patient_check.toggled.connect(self.patient_changed.emit)
        self.patient_opacity.valueChanged.connect(self.patient_changed.emit)
        settings_layout.addLayout(patient_controls)
        template_3d_controls = QtWidgets.QHBoxLayout()
        self.template_3d_check = QtWidgets.QCheckBox("3D 显示模板软骨参考")
        self.template_3d_check.setChecked(True)
        template_3d_controls.addWidget(self.template_3d_check)
        template_3d_controls.addWidget(QtWidgets.QLabel("不透明度"))
        self.template_3d_opacity = QtWidgets.QSlider(Qt.Horizontal)
        self.template_3d_opacity.setRange(0, 100)
        self.template_3d_opacity.setValue(35)
        self.template_3d_opacity.setMaximumWidth(180)
        template_3d_controls.addWidget(self.template_3d_opacity)
        self.template_3d_opacity_text = QtWidgets.QLabel("35%")
        template_3d_controls.addWidget(self.template_3d_opacity_text)
        template_3d_controls.addWidget(QtWidgets.QLabel("紫色：配准后的模板软骨"))
        template_3d_controls.addStretch()
        self.template_3d_check.toggled.connect(self.surface_changed.emit)
        self.template_3d_opacity.valueChanged.connect(self.surface_changed.emit)
        settings_layout.addLayout(template_3d_controls)

    def install_sections(self, parts, cartilage_check):
        panel=self.display_settings_panel
        old=panel.layout()
        overlays=QtWidgets.QWidget()
        overlays.setLayout(old)
        overlays.layout().insertWidget(0, cartilage_check)
        tabs=QtWidgets.QTabWidget(panel)
        tabs.addTab(overlays,"覆盖与叠加")
        parts.setParent(tabs)
        parts.setWindowFlags(Qt.Widget)
        tabs.addTab(parts,"部件与透明度")
        layout=QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(8,8,8,8)
        layout.addWidget(tabs)

    def open_from(self, anchor_widget):
        panel=self.display_settings_panel
        if panel.isVisible():
            panel.hide()
            return
        panel.adjustSize()
        anchor=anchor_widget.mapToGlobal(QPoint(0,anchor_widget.height()))
        screen=QtWidgets.QApplication.screenAt(anchor) or QtWidgets.QApplication.primaryScreen()
        bounds=screen.availableGeometry()
        panel.move(max(bounds.left(),min(anchor.x(),bounds.right()-panel.width()+1)),
                   max(bounds.top(),min(anchor.y(),bounds.bottom()-panel.height()+1)))
        panel.show()
        panel.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible() and hasattr(self, "display_settings_panel"):
            self.resize_display_settings()

    def resize_display_settings(self):
        # Natural content width, shared by the header and floating panel.
        panel_layout = self.display_settings_panel.layout()
        width = max(panel_layout.sizeHint().width() + 2 * self.display_settings_panel.frameWidth(),
                    self.display_settings_toggle.sizeHint().width())
        self.display_settings_toggle.setFixedWidth(width)
        self.display_settings_panel.setFixedWidth(width)
        self.display_settings_panel.adjustSize()

    def toggle_display_settings(self, expanded):
        self.display_settings_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        panel = self.display_settings_panel
        if not expanded:
            panel.hide()
            return
        self.resize_display_settings()
        anchor = self.display_settings_toggle.mapToGlobal(
            QPoint(0, self.display_settings_toggle.height()))
        screen = QtWidgets.QApplication.screenAt(anchor) or QtWidgets.QApplication.primaryScreen()
        available = screen.availableGeometry()
        x = max(available.left(), min(anchor.x(), available.right() - panel.width() + 1))
        y = anchor.y()
        if y + panel.height() > available.bottom() + 1:
            y = self.display_settings_toggle.mapToGlobal(QPoint(0, 0)).y() - panel.height()
        panel.move(x, max(available.top(), y))
        panel.show()
        panel.raise_()

