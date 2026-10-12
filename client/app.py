import json
import os
import sys
from pathlib import Path
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QTimer, QElapsedTimer, QSize
import vtkmodules.all as vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

if __package__:
    from . import vtk_loader
    from .AnalysisWorker import AnalysisWorker
    from .modify_dialog import seg_modify_dialog
else:
    import vtk_loader
    from AnalysisWorker import AnalysisWorker
    from modify_dialog import seg_modify_dialog


class NiftiSurfaceViewer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.server_url = os.environ.get("KNEE_SERVER_URL", "http://127.0.0.1:8000")
        self.current_nii_path = None
        self.current_volume = self.current_seg_volume = None
        self.case_id = self.task_id = self.operation = None
        self.worker = None
        self.pending = False
        self.closing = False
        self.selected_labels = [True] * 5
        self.opacity_labels = [70] * 5
        self.subject_actors = {}
        self.coverage_actors = {}
        self.slice_actors = {}
        self.slice_stacks = {}
        self.template_overlays = {}
        self.patient_overlays = {}
        self.template_3d_actors = {}
        self.registration_done = False
        self.metrics = None
        self.coverage_manifest = None
        self.registration_qc = None
        self.seg_modify_dialog = seg_modify_dialog(self)
        self.seg_modify_dialog.setting_applied.connect(self.apply_modify_settings)
        self.create_menu()

        frame = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(frame)
        controls = QtWidgets.QHBoxLayout()
        self.side = QtWidgets.QComboBox()
        self.side.addItem("请选择左右膝", None)
        self.side.addItem("右膝", "right")
        self.side.addItem("左膝（当前未配置配准模板）", "left")
        controls.addWidget(self.side)
        self.coverage_check = QtWidgets.QCheckBox("显示覆盖 / 缺损标注")
        self.coverage_check.setChecked(True)
        self.cartilage_check = QtWidgets.QCheckBox("分析时叠加软骨")
        self.cartilage_check.setChecked(False)
        for check in (self.coverage_check, self.cartilage_check):
            controls.addWidget(check)
            check.toggled.connect(self.render_surface)
        self.legend = QtWidgets.QLabel(
            '<span style="color:#2dbe50">■ 软骨覆盖</span>　'
            '<span style="color:#e63232">■ 估计全层缺损</span>　'
            '<span style="color:#888">■ 未纳入分析范围</span>')
        controls.addWidget(self.legend)
        layout.addLayout(controls)
        overlay_controls = QtWidgets.QHBoxLayout()
        self.template_check = QtWidgets.QCheckBox("MRI 叠加模板软骨参考")
        self.template_check.setChecked(True)
        self.template_check.toggled.connect(self.update_template_overlay)
        overlay_controls.addWidget(self.template_check)
        overlay_controls.addWidget(QtWidgets.QLabel("不透明度"))
        self.template_opacity = QtWidgets.QSlider(Qt.Horizontal)
        self.template_opacity.setRange(0, 100)
        self.template_opacity.setValue(40)
        self.template_opacity.setMaximumWidth(180)
        self.template_opacity.valueChanged.connect(self.update_template_overlay)
        overlay_controls.addWidget(self.template_opacity)
        self.template_opacity_text = QtWidgets.QLabel("40%")
        overlay_controls.addWidget(self.template_opacity_text)
        overlay_controls.addWidget(QtWidgets.QLabel('<span style="color:#cc40ff">■ 模板软骨参考</span>（非厚度差值）'))
        overlay_controls.addStretch()
        layout.addLayout(overlay_controls)
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
        self.patient_check.toggled.connect(self.update_patient_overlay)
        self.patient_opacity.valueChanged.connect(self.update_patient_overlay)
        layout.addLayout(patient_controls)
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
        self.template_3d_check.toggled.connect(self.render_surface)
        self.template_3d_opacity.valueChanged.connect(self.render_surface)
        layout.addLayout(template_3d_controls)
        grid = QtWidgets.QGridLayout()
        layout.addLayout(grid, 1)
        self.widgets = {}
        self.renderers = {}
        self.slice_sliders = {}
        self.slice_labels = {}
        for key, title, row, col in (
            ("3d", "三维模型 / 软骨覆盖与估计缺损", 0, 0),
            ("z", "Z 方向切片", 0, 1),
            ("x", "X 方向切片", 1, 0),
            ("y", "Y 方向切片", 1, 1),
        ):
            panel = QtWidgets.QGroupBox(title)
            box = QtWidgets.QVBoxLayout(panel)
            widget = QVTKRenderWindowInteractor(panel)
            box.addWidget(widget, 1)
            if key != "3d":
                slice_row = QtWidgets.QHBoxLayout()
                slider = QtWidgets.QSlider(Qt.Horizontal)
                slider.setRange(0, 0)
                slider.setEnabled(False)
                slider.setSingleStep(1)
                slider.setToolTip("拖动浏览切片；方向键逐层移动")
                label = QtWidgets.QLabel("未加载")
                slice_row.addWidget(slider, 1)
                slice_row.addWidget(label)
                box.addLayout(slice_row)
                self.slice_sliders[key] = slider
                self.slice_labels[key] = label
                slider.valueChanged.connect(lambda value, axis=key: self.change_slice(axis, value))
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
        self.setCentralWidget(frame)
        self.progress = None
        self.elapsed = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress)
        self.status_text = "就绪，请打开 MRI"
        self.initialized = False
        self.update_actions()

    def create_menu(self):
        toolbar = QtWidgets.QToolBar("常用功能", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        self.actions = {}
        entries = [
            ("open", "打开文件", self.open_raw_nii_gz),
            ("seg", "分割 / 显示设置", self.show_modify_dialog),
            ("reg", "配准", lambda: self.start_operation("registration")),
            ("morph", "计算指标 / 缺损", lambda: self.start_operation("morphometry")),
            ("metrics", "指标结果", self.show_metrics),
            ("resume", "继续等待 / 重取结果", self.resume_task),
            ("retry", "重新提交任务", self.retry_task),
            ("qc", "配准质控", self.show_qc),
            ("template", "载入已有配准标签", self.open_template_overlay),
            ("reset", "恢复默认", self.default_back),
        ]
        menu = self.menuBar().addMenu("功能")
        for key, text, slot in entries:
            action = QtWidgets.QAction(text, self)
            action.triggered.connect(slot)
            toolbar.addAction(action)
            menu.addAction(action)
            self.actions[key] = action

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def update_actions(self):
        busy = self.busy()
        self.actions["open"].setEnabled(not busy)
        self.actions["seg"].setEnabled(self.current_volume is not None and not busy and not self.pending)
        self.actions["reg"].setEnabled(self.current_seg_volume is not None and not busy and not self.pending)
        self.actions["morph"].setEnabled(self.registration_done and not busy and not self.pending)
        self.actions["metrics"].setEnabled(self.metrics is not None)
        self.coverage_check.setEnabled(bool(self.coverage_actors))
        self.cartilage_check.setEnabled(bool(self.coverage_actors))
        self.legend.setVisible(bool(self.coverage_actors))
        self.template_check.setEnabled(bool(self.template_overlays))
        self.patient_check.setEnabled(bool(self.patient_overlays))
        self.patient_opacity.setEnabled(bool(self.patient_overlays))
        self.template_opacity.setEnabled(bool(self.template_overlays))
        self.template_3d_check.setEnabled(bool(self.template_3d_actors))
        self.template_3d_opacity.setEnabled(bool(self.template_3d_actors))
        self.actions["template"].setEnabled(self.current_volume is not None and not busy and not self.pending)
        self.actions["resume"].setEnabled(bool(self.task_id) and self.pending and not busy)
        self.actions["retry"].setEnabled(bool(self.operation) and self.pending and not busy)
        self.actions["qc"].setEnabled(self.registration_qc is not None)
        self.side.setEnabled(not busy and self.case_id is None and not self.pending)
        self.seg_modify_dialog.set_busy(busy or self.pending)

    def open_raw_nii_gz(self):
        if self.busy():
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 MRI", "", "NIfTI (*.nii.gz)")
        if not path:
            return
        if self.pending:
            answer = QtWidgets.QMessageBox.question(self, "切换病例", "旧任务可能仍在服务器运行。切换后本窗口不再跟踪它，是否继续？")
            if answer != QtWidgets.QMessageBox.Yes:
                return
        try:
            volume = vtk_loader.load_volume(path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "读取失败", str(exc))
            return
        self.current_nii_path, self.current_volume = path, volume
        self.case_id = self.task_id = self.operation = None
        self.pending = False
        self.side.setCurrentIndex(0)
        self.current_seg_volume = None
        self.registration_done = False
        self.metrics = self.coverage_manifest = None
        self.registration_qc = None
        self.subject_actors.clear()
        self.coverage_actors.clear()
        self.clear_template_overlay()
        self.clear_patient_overlay()
        self.ren_3d.RemoveAllViewProps()
        self.vtk_widget.GetRenderWindow().Render()
        self.slice_actors = vtk_loader.create_slice_actors(volume)
        self.slice_stacks = {}
        for key, actor in self.slice_actors.items():
            renderer = self.renderers[key]
            renderer.RemoveAllViewProps()
            stack = vtk.vtkImageStack()
            actor.GetProperty().SetLayerNumber(0)
            stack.AddImage(actor)
            stack.SetActiveLayer(0)
            self.slice_stacks[key] = stack
            renderer.AddViewProp(stack)
            renderer.ResetCamera()
            self.widgets[key].GetRenderWindow().Render()
        self.statusBar().showMessage(f"已加载：{Path(path).name}；请选择左右膝")
        self.reset_slice_positions()
        self.update_actions()

    def change_slice(self, axis, index):
        if self.current_volume is None or axis not in self.slice_actors:
            return
        vtk_loader.set_slice_index(
            self.current_volume, axis, index, self.slice_actors[axis],
            self.template_overlays.get(axis))
        if axis in self.patient_overlays:
            vtk_loader.set_slice_index(
                self.current_volume, axis, index, self.slice_actors[axis],
                self.patient_overlays[axis])
        total = self.current_volume.shape[{"x": 0, "y": 1, "z": 2}[axis]]
        self.slice_labels[axis].setText(f"{index + 1} / {total}")
        self.widgets[axis].GetRenderWindow().Render()

    def reset_slice_positions(self):
        if self.current_volume is None:
            return
        for axis, slider in self.slice_sliders.items():
            total = self.current_volume.shape[{"x": 0, "y": 1, "z": 2}[axis]]
            slider.blockSignals(True)
            slider.setRange(0, total - 1)
            slider.setValue(total // 2)
            slider.setEnabled(True)
            slider.blockSignals(False)
            self.change_slice(axis, total // 2)

    def show_modify_dialog(self):
        self.seg_modify_dialog.set_settings(self.selected_labels, self.opacity_labels)
        self.seg_modify_dialog.set_has_segmentation(self.current_seg_volume is not None)
        self.seg_modify_dialog.show()
        self.seg_modify_dialog.raise_()

    def apply_modify_settings(self, selected, opacity):
        self.selected_labels, self.opacity_labels = selected.copy(), opacity.copy()
        if self.subject_actors:
            self.render_surface()
        else:
            self.start_operation("segmentation")

    def start_operation(self, operation, resume=False):
        if self.busy() or not self.current_nii_path:
            return
        if self.pending and not resume:
            return
        side = self.side.currentData()
        if side is None:
            QtWidgets.QMessageBox.information(self, "选择左右膝", "请先选择实际的左右膝。")
            return
        if operation in {"registration", "morphometry"} and side != "right":
            QtWidgets.QMessageBox.information(self, "模板未配置", "当前只配置右膝模板，暂不启动左膝配准。")
            return
        if operation == "registration" and not self.case_id:
            return
        if operation == "morphometry" and not self.registration_done:
            return
        if not resume:
            self.task_id = None
            if operation == "segmentation":
                self.clear_patient_overlay()
            # Hide obsolete metrics/geometry before any recomputation.
            self.coverage_actors.clear()
            self.metrics = self.coverage_manifest = None
            if operation in {"segmentation", "registration"}:
                self.clear_template_overlay()
                self.registration_done = False
                self.registration_qc = None
            self.rebuild_scene()
        self.operation = operation
        self.pending = True
        self.worker = AnalysisWorker(
            operation=operation, file_path=self.current_nii_path,
            knee_side=side, case_id=self.case_id,
            task_id=self.task_id if resume else None,
            save_dir=str(Path(__file__).resolve().parent / "cache"),
            server_url=self.server_url, parent=self,
        )
        self.worker.case_created.connect(self.on_case_created)
        self.worker.task_created.connect(self.on_task_created)
        self.worker.status_changed.connect(self.on_status)
        self.worker.result_ready.connect(self.on_result)
        self.worker.failed.connect(self.on_failed)
        self.worker.waiting_stopped.connect(self.on_stopped)
        self.worker.finished.connect(self.on_worker_finished)

        # 每次真正启动任务时才创建进度框
        if self.progress is not None:
            self.progress.deleteLater()

        self.progress = QtWidgets.QProgressDialog(
            "", "停止等待", 0, 0, self
        )
        self.progress.setWindowTitle("MRI 处理任务")
        self.progress.setWindowModality(Qt.NonModal)
        self.progress.setMinimumWidth(460)
        self.progress.setMinimumDuration(0)
        self.progress.setAutoClose(False)
        self.progress.setAutoReset(False)
        self.progress.canceled.connect(self.stop_waiting)

        self.status_text = "正在连接服务器…"
        self.elapsed.start()
        self.update_progress()
        self.progress.show()
        self.timer.start(1000)
        self.worker.start()
        self.update_actions()

    def on_case_created(self, value):
        self.case_id = value

    def on_task_created(self, value):
        self.task_id = value

    def on_status(self, text):
        self.status_text = text
        self.statusBar().showMessage(text)
        self.update_progress()

    def update_progress(self):

        if self.progress is None:
            return

        seconds = self.elapsed.elapsed() // 1000 if self.elapsed.isValid() else 0
        self.progress.setLabelText(f"{self.status_text}\n已用时间：{seconds//60:02d}:{seconds%60:02d}\n停止等待不会取消服务器计算。")

    def stop_waiting(self):
        if self.busy():
            self.worker.stop_waiting()
            self.statusBar().showMessage("正在停止本地等待，等待当前网络请求返回…")

    def on_stopped(self):
        self.status_text = "已停止等待；服务器任务可能仍在运行，可点击继续等待"

    def on_failed(self, error):
        self.status_text = "任务或结果加载失败；可继续查询原任务，或确认失败后重新提交"
        QtWidgets.QMessageBox.warning(self, "处理失败", error)

    def resume_task(self):
        if self.task_id:
            self.start_operation(self.operation, resume=True)

    def retry_task(self):
        answer = QtWidgets.QMessageBox.question(self, "确认重新提交", "请先确认原任务已失败。若只是网络中断，请优先继续等待，避免重复计算。仍要重新提交吗？")
        if answer == QtWidgets.QMessageBox.Yes:
            self.pending = False
            self.start_operation(self.operation)

    def on_result(self, result):
        if result["case_id"] != self.case_id:
            return
        try:
            if result["operation"] == "segmentation":
                volume = vtk_loader.load_volume(result["files"]["segmentation"], self.current_volume, labels=True)
                actors = vtk_loader.create_surface_actors(volume)
                if not actors:
                    raise ValueError("分割结果中没有可显示的组织")
                self.current_seg_volume, self.subject_actors = volume, actors
                self.load_patient_overlay(volume)
                self.coverage_actors = {}
                self.registration_done = False
                self.registration_qc = None
            elif result["operation"] == "registration":
                qc = json.loads(Path(result["files"]["qc"]).read_text(encoding="utf-8"))
                self.load_template_overlay(result["files"]["registration"])
                self.registration_qc = qc
                self.registration_done = True
            elif result["operation"] == "morphometry":
                manifest = json.loads(Path(result["files"]["coverage_manifest"]).read_text(encoding="utf-8"))
                if manifest.get("coordinate_system") != "NIfTI RAS" or manifest.get("units") != "mm":
                    raise ValueError("分析网格坐标约定不兼容；需要 NIfTI RAS / mm")
                actors = vtk_loader.load_coverage_actors(result["files"]["bone_coverage"])
                self.coverage_actors = actors
                self.metrics = result["metrics"]
                self.coverage_manifest = manifest
                self.coverage_check.setChecked(True)
                self.cartilage_check.setChecked(False)
            else:
                raise ValueError("此界面只处理分割、配准和指标计算任务")
            self.rebuild_scene()
            if result["operation"] == "segmentation":
                self.ren_3d.ResetCamera()
            self.ren_3d.ResetCameraClippingRange()
            self.vtk_widget.GetRenderWindow().Render()
            self.seg_modify_dialog.set_has_segmentation(True)
            self.pending = False
            self.task_id = None
            self.status_text = {
                "segmentation": "分割已显示，可继续配准",
                "registration": "配准完成：紫色为模板软骨参考，可调整叠加不透明度",
                "morphometry": "计算完成：绿色为软骨覆盖，红色为估计全层缺损，灰色为未纳入分析范围",
            }[result["operation"]]
        except Exception as exc:
            self.on_failed(str(exc))

    def rebuild_scene(self):
        self.ren_3d.RemoveAllViewProps()
        for actor in (list(self.subject_actors.values()) + list(self.coverage_actors.values())
                      + list(self.template_3d_actors.values())):
            self.ren_3d.AddActor(actor)
        self.render_surface()

    def clear_template_overlay(self):
        for actor in self.template_3d_actors.values():
            self.ren_3d.RemoveActor(actor)
        self.template_3d_actors = {}
        for key, actor in self.template_overlays.items():
            self.slice_stacks[key].RemoveImage(actor)
        self.template_overlays = {}
        self.update_template_overlay()
        self.render_surface()

    def clear_patient_overlay(self):
        for key, actor in self.patient_overlays.items():
            self.slice_stacks[key].RemoveImage(actor)
        self.patient_overlays = {}
        self.update_patient_overlay()

    def load_patient_overlay(self, volume):
        overlays = vtk_loader.create_patient_overlays(volume, self.slice_actors)
        self.clear_patient_overlay()
        self.patient_overlays = overlays
        for key, actor in overlays.items():
            self.slice_stacks[key].AddImage(actor)
        self.patient_check.setChecked(True)
        self.update_patient_overlay()

    def update_patient_overlay(self, *_):
        opacity = self.patient_opacity.value() / 100
        self.patient_opacity_text.setText(f"{self.patient_opacity.value()}%")
        for actor in self.patient_overlays.values():
            actor.SetVisibility(self.patient_check.isChecked())
            actor.GetProperty().SetOpacity(opacity)
        for key in self.slice_stacks:
            self.widgets[key].GetRenderWindow().Render()

    def load_template_overlay(self, path):
        volume = vtk_loader.load_volume(path, self.current_volume, labels=True)
        overlays = vtk_loader.create_template_overlays(volume, self.slice_actors)
        actors_3d = vtk_loader.create_template_cartilage_actors(volume)
        self.clear_template_overlay()
        self.template_3d_actors = actors_3d
        self.template_overlays = overlays
        for key, actor in overlays.items():
            self.slice_stacks[key].AddImage(actor)
        self.template_check.setChecked(True)
        self.template_3d_check.setChecked(True)
        self.update_template_overlay()
        self.rebuild_scene()
        if not self.subject_actors and not self.coverage_actors:
            self.ren_3d.ResetCamera()
        self.ren_3d.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()

    def update_template_overlay(self, *_):
        opacity = self.template_opacity.value() / 100
        self.template_opacity_text.setText(f"{self.template_opacity.value()}%")
        for key, actor in self.template_overlays.items():
            actor.SetVisibility(self.template_check.isChecked())
            actor.GetProperty().SetOpacity(opacity)
        for key in self.slice_stacks:
            self.widgets[key].GetRenderWindow().Render()

    def open_template_overlay(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择当前病例的 warped_template_seg.nii.gz（已配准标签）", "", "NIfTI (*.nii.gz)")
        if not path:
            return
        try:
            self.load_template_overlay(path)
            self.update_actions()
            self.statusBar().showMessage("已载入模板软骨参考；请确认标签来自当前病例的配准结果")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "模板叠加失败", str(exc))

    def render_surface(self, *_):
        opacity = self.template_3d_opacity.value() / 100
        self.template_3d_opacity_text.setText(f"{self.template_3d_opacity.value()}%")
        for actor in self.template_3d_actors.values():
            actor.SetVisibility(self.template_3d_check.isChecked())
            actor.GetProperty().SetOpacity(opacity)
        analysis = bool(self.coverage_actors) and self.coverage_check.isChecked()
        for label, actor in self.subject_actors.items():
            # Hide preview bone while metric bone is shown: no duplicate surfaces.
            visible = self.selected_labels[label-1]
            if analysis:
                visible = visible and label not in (1, 3) and self.cartilage_check.isChecked()
            actor.SetVisibility(visible)
            actor.GetProperty().SetOpacity(self.opacity_labels[label-1] / 100)
        for label, actor in self.coverage_actors.items():
            actor.SetVisibility(analysis and self.selected_labels[label-1])
            # Opaque analysis faces keep red/green categorical coloring readable.
            actor.GetProperty().SetOpacity(1.0)
        if hasattr(self, "vtk_widget"):
            self.vtk_widget.GetRenderWindow().Render()

    def default_back(self):
        self.patient_check.setChecked(True)
        self.patient_opacity.setValue(40)
        self.reset_slice_positions()
        self.selected_labels, self.opacity_labels = [True]*5, [70]*5
        self.seg_modify_dialog.set_settings(self.selected_labels, self.opacity_labels)
        self.coverage_check.setChecked(True)
        self.cartilage_check.setChecked(False)
        self.template_check.setChecked(True)
        self.template_opacity.setValue(40)
        self.template_3d_check.setChecked(True)
        self.template_3d_opacity.setValue(35)
        self.render_surface()

    def show_metrics(self):
        if self.metrics is None:
            return
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("形态学指标（覆盖面积为 cAB）")
        dialog.resize(850, 620)
        layout = QtWidgets.QVBoxLayout(dialog)
        regions = self.metrics.get("regions", {})
        table = QtWidgets.QTableWidget(len(regions), 5)
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
        dialog.exec_()
        dialog.deleteLater()

    def show_qc(self):
        QtWidgets.QMessageBox.information(self, "配准质控", json.dumps(self.registration_qc, ensure_ascii=False, indent=2))

    def on_worker_finished(self):
        self.timer.stop()
        self.progress.hide()
        old = self.worker
        self.worker = None
        old.deleteLater()
        self.statusBar().showMessage(self.status_text)
        self.update_actions()
        if self.closing:
            QTimer.singleShot(0, self.close)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.initialized:
            for widget in self.widgets.values():
                widget.GetRenderWindow().GetInteractor().Initialize()
                widget.GetRenderWindow().Render()
            self.initialized = True

    def closeEvent(self, event):
        if self.busy():
            self.closing = True
            self.stop_waiting()
            event.ignore()
            return
        self.timer.stop()
        for widget in self.widgets.values():
            widget.Finalize()
        event.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = NiftiSurfaceViewer()
    window.setWindowTitle("膝关节 MRI：形态分析与软骨缺损")
    window.resize(1200, 850)
    window.show()
    sys.exit(app.exec_())
