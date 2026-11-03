import json
import os
import sys
from pathlib import Path
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QTimer, QElapsedTimer, QSize, QPoint
import vtkmodules.all as vtk
from pathlib import Path
from PyQt5.QtGui import QIcon

if __package__:
    from .widgets.theme import apply_theme
    from .widgets.analysis_controls import make_toolbar, AnalysisDialog
    from .widgets.thickness_views import ThicknessViews
    from .widgets import (KneeSideSwitch, seg_modify_dialog, DisplaySettingsWidget,
                          ProgressPanel, ViewGrid, MetricsDialog, TaskProgressDialog)
    from . import vtk_loader
    from .AnalysisWorker import AnalysisWorker
else:
    from widgets.theme import apply_theme
    from widgets.analysis_controls import make_toolbar, AnalysisDialog
    from widgets.thickness_views import ThicknessViews
    from widgets import (KneeSideSwitch, seg_modify_dialog, DisplaySettingsWidget,
                         ProgressPanel, ViewGrid, MetricsDialog, TaskProgressDialog)
    import vtk_loader
    from AnalysisWorker import AnalysisWorker


class NiftiSurfaceViewer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        apply_theme(QtWidgets.QApplication.instance())
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
        self.thickness_views = ThicknessViews(self)
        self.create_menu()

        frame = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(frame)
        self.progress_panel = ProgressPanel(self)

        controls = QtWidgets.QHBoxLayout()
        self.case_label = QtWidgets.QLabel("当前文件：未加载")
        self.case_label.setMinimumWidth(0)
        self.case_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        controls.addWidget(self.case_label, 1)
        controls.addWidget(QtWidgets.QLabel("膝关节侧别"))
        self.side = KneeSideSwitch()
        controls.addWidget(self.side)
        self.case_status = QtWidgets.QLabel("就绪")
        controls.addWidget(self.case_status)
        self.cartilage_check = QtWidgets.QCheckBox("分析时叠加软骨")
        self.cartilage_check.toggled.connect(self.render_surface)

        layout.addLayout(controls)
        self.display_settings = DisplaySettingsWidget(self)
        self.display_settings.surface_changed.connect(self.render_surface)
        self.display_settings.template_changed.connect(self.update_template_overlay)
        self.display_settings.patient_changed.connect(self.update_patient_overlay)
        self.display_settings.hide()
        self.display_settings.install_sections(self.seg_modify_dialog, self.cartilage_check)
        self.seg_modify_dialog.close_button.clicked.connect(self.display_settings.display_settings_panel.hide)
        self.view_grid = ViewGrid(self)
        self.view_grid.slice_changed.connect(self.change_slice)
        layout.addWidget(self.view_grid, 1)
        layout.addWidget(self.progress_panel)
        self.statusBar().hide()
        self.setCentralWidget(frame)
        self.progress = None
        self.elapsed = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress)
        self.status_text = "就绪，请打开 MRI"
        self.initialized = False
        self.update_actions()

    def create_menu(self):
        icons=QtWidgets.QStyle
        entries=[
            ("open","打开文件",self.open_raw_nii_gz,icons.SP_DialogOpenButton,"打开 MRI"),
            ("analysis","分析",self.show_analysis_dialog,icons.SP_MediaPlay,"一键分析或选择分割、配准、计算指标"),
            ("display","显示设置",self.show_display_settings,icons.SP_FileDialogContentsView,"调整分割部件与不透明度"),
            ("metrics","指标报告",self.show_metrics,icons.SP_FileDialogDetailedView,"查看分区指标"),
            ("thickness","热力图",self.thickness_views.show,icons.SP_DesktopIcon,"查看厚度和分区 FCL"),
            ("resume","继续等待",self.resume_task,icons.SP_MediaSkipForward,"继续等待 / 重取结果"),
            ("retry","重新提交",self.retry_task,icons.SP_BrowserReload,"确认原任务失败后重新提交"),
            ("qc","配准质控",self.show_qc,icons.SP_DialogApplyButton,"查看配准质控"),
            ("template","载入模板",self.open_template_overlay,icons.SP_DirOpenIcon,"载入当前病例的已有配准标签"),
            ("reset","恢复默认",self.default_back,icons.SP_DialogResetButton,"恢复显示默认设置"),
        ]
        self.actions=make_toolbar(self,entries)
        # Internal step actions retain the existing prerequisite logic.
        for key in ("seg","reg","morph"):
            self.actions[key]=QtWidgets.QAction(self)

    def show_analysis_dialog(self):
        self.update_actions()
        enabled={operation:self.actions[key].isEnabled() for operation,key in
                 (("analysis","analysis"),("segmentation","seg"),
                  ("registration","reg"),("morphometry","morph"))}
        dialog=AnalysisDialog(enabled,self.side.currentData(),self)
        if dialog.exec_()==QtWidgets.QDialog.Accepted and dialog.operation:
            self.start_operation(dialog.operation)
        dialog.deleteLater()

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def update_actions(self):
        busy = self.busy()
        self.actions["thickness"].setEnabled(bool(self.thickness_views.windows) and not busy)
        self.actions["open"].setEnabled(not busy)
        self.actions["display"].setEnabled(self.current_volume is not None and not busy)
        self.actions["analysis"].setEnabled(self.current_volume is not None and not busy and not self.pending)
        self.actions["seg"].setEnabled(self.current_volume is not None and not busy and not self.pending)
        self.actions["reg"].setEnabled(self.current_seg_volume is not None and not busy and not self.pending)
        self.actions["morph"].setEnabled(self.registration_done and not busy and not self.pending)
        self.actions["metrics"].setEnabled(self.metrics is not None)
        self.display_settings.coverage_check.setEnabled(bool(self.coverage_actors))
        self.cartilage_check.setEnabled(bool(self.coverage_actors))
        self.display_settings.legend.setVisible(bool(self.coverage_actors) and self.display_settings.coverage_check.isChecked())
        self.display_settings.template_check.setEnabled(bool(self.template_overlays))
        self.display_settings.patient_check.setEnabled(bool(self.patient_overlays))
        self.display_settings.patient_opacity.setEnabled(bool(self.patient_overlays))
        self.display_settings.template_opacity.setEnabled(bool(self.template_overlays))
        self.display_settings.template_3d_check.setEnabled(bool(self.template_3d_actors))
        self.display_settings.template_3d_opacity.setEnabled(bool(self.template_3d_actors))
        self.actions["template"].setEnabled(self.current_volume is not None and not busy and not self.pending)
        self.actions["resume"].setEnabled(bool(self.task_id) and self.pending and not busy)
        self.actions["retry"].setEnabled(bool(self.operation) and self.pending and not busy)
        self.actions["qc"].setEnabled(self.registration_qc is not None)
        self.side.setEnabled(not busy and self.case_id is None and not self.pending)
        self.seg_modify_dialog.set_busy(busy or self.pending or self.current_seg_volume is None)
        self.case_status.setText("处理中" if busy else ("待处理 / 可恢复" if self.pending else ("已完成" if self.metrics is not None else "就绪")))

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
        self.thickness_views.clear()
        self.current_nii_path, self.current_volume = path, volume
        self.case_label.setText("当前文件：" + Path(path).name)
        self.case_label.setToolTip(str(path))
        self.on_phase(0, "已加载 MRI，选择左右膝后可一键分析")
        self.case_id = self.task_id = self.operation = None
        self.pending = False
        self.side.setChecked(False)
        self.current_seg_volume = None
        self.registration_done = False
        self.metrics = self.coverage_manifest = None
        self.registration_qc = None
        self.subject_actors.clear()
        self.coverage_actors.clear()
        self.clear_template_overlay()
        self.clear_patient_overlay()
        self.view_grid.ren_3d.RemoveAllViewProps()
        self.view_grid.vtk_widget.GetRenderWindow().Render()
        self.slice_actors = vtk_loader.create_slice_actors(volume)
        self.slice_stacks = {}
        for key, actor in self.slice_actors.items():
            renderer = self.view_grid.renderers[key]
            renderer.RemoveAllViewProps()
            stack = vtk.vtkImageStack()
            actor.GetProperty().SetLayerNumber(0)
            stack.AddImage(actor)
            stack.SetActiveLayer(0)
            self.slice_stacks[key] = stack
            renderer.AddViewProp(stack)
            renderer.ResetCamera()
            self.view_grid.widgets[key].GetRenderWindow().Render()
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
        self.view_grid.slice_labels[axis].setText(f"{index + 1} / {total}")
        self.view_grid.widgets[axis].GetRenderWindow().Render()

    def reset_slice_positions(self):
        if self.current_volume is None:
            return
        for axis, slider in self.view_grid.slice_sliders.items():
            total = self.current_volume.shape[{"x": 0, "y": 1, "z": 2}[axis]]
            slider.blockSignals(True)
            slider.setRange(0, total - 1)
            slider.setValue(total // 2)
            slider.setEnabled(True)
            slider.blockSignals(False)
            self.change_slice(axis, total // 2)

    def show_display_settings(self):
        self.seg_modify_dialog.show()
        self.seg_modify_dialog.set_settings(self.selected_labels, self.opacity_labels)
        self.seg_modify_dialog.set_has_segmentation(self.current_seg_volume is not None)
        self.display_settings.open_from(self.toolbar_buttons["display"])

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
        if operation in {"registration", "morphometry", "analysis"} and side != "right":
            QtWidgets.QMessageBox.information(self, "模板未配置", "当前选择左膝，但服务器仅配置右膝模板。若影像是右膝，请在上传前切换为右膝；若确为左膝，需要先配置左膝模板。")
            return
        if operation == "registration" and not self.case_id:
            return
        if operation == "morphometry" and not self.registration_done:
            return
        if not resume:
            self.thickness_views.clear()
            self.task_id = None
            if operation == "segmentation":
                self.clear_patient_overlay()
                self.current_seg_volume = None
                self.subject_actors.clear()
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
        self.worker.phase_changed.connect(self.on_phase)
        self.worker.result_ready.connect(self.on_result)
        self.worker.failed.connect(self.on_failed)
        self.worker.waiting_stopped.connect(self.on_stopped)
        self.worker.finished.connect(self.on_worker_finished)

        # 每次真正启动任务时才创建进度框
        if self.progress is not None:
            self.progress.deleteLater()

        self.progress = TaskProgressDialog(self)
        self.progress.canceled.connect(self.stop_waiting)
        self.on_phase(0, "正在恢复查询" if resume else "准备开始")

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
        self.progress_panel.pipeline_label.setText(text)
        self.update_progress()

    def on_phase(self, value, text):
        self.progress_panel.pipeline_label.setText(text)
        self.progress_panel.pipeline_bar.setValue(value)
        self.progress_panel.pipeline_bar.setVisible(0 < value < 5)
        if getattr(self, "progress", None) is not None:
            self.progress.setValue(value)

    def update_progress(self):

        if self.progress is None:
            return

        seconds = self.elapsed.elapsed() // 1000 if self.elapsed.isValid() else 0
        self.progress_panel.elapsed_label.setText(f"已用 {seconds//60:02d}:{seconds%60:02d}")
        self.progress.setLabelText(f"{self.status_text}\n已用时间：{seconds//60:02d}:{seconds%60:02d}\n停止等待不会取消服务器计算。")

    def stop_waiting(self):
        if self.busy():
            self.worker.stop_waiting()
            self.statusBar().showMessage("正在停止本地等待，等待当前网络请求返回…")

    def on_stopped(self):
        self.status_text = "已停止等待；服务器任务可能仍在运行，可点击继续等待"
        self.progress_panel.pipeline_label.setText(self.status_text)
        self.progress_panel.pipeline_bar.setFormat("已停止本地等待")

    def on_failed(self, error):
        self.status_text = "任务或结果加载失败；可继续查询原任务，或确认失败后重新提交"
        self.progress_panel.pipeline_label.setText("处理失败，详情见弹窗；可重取结果或重新提交")
        self.progress_panel.pipeline_bar.setFormat("处理失败")
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
            operation = result["operation"]
            if operation not in {"segmentation", "registration", "morphometry", "analysis"}:
                raise ValueError("未知任务类型")
            if operation in {"segmentation", "analysis"}:
                volume = vtk_loader.load_volume(result["files"]["segmentation"], self.current_volume, labels=True)
                actors = vtk_loader.create_surface_actors(volume)
                if not actors:
                    raise ValueError("分割结果中没有可显示的组织")
                self.current_seg_volume, self.subject_actors = volume, actors
                self.load_patient_overlay(volume)
                self.coverage_actors = {}
                self.registration_done = False
                self.registration_qc = None
            if operation in {"registration", "analysis"}:
                qc = json.loads(Path(result["files"]["qc"]).read_text(encoding="utf-8"))
                self.load_template_overlay(result["files"]["registration"])
                self.registration_qc = qc
                self.registration_done = True
            if operation in {"morphometry", "analysis"}:
                manifest = json.loads(Path(result["files"]["coverage_manifest"]).read_text(encoding="utf-8"))
                if manifest.get("coordinate_system") != "NIfTI RAS" or manifest.get("units") != "mm":
                    raise ValueError("分析网格坐标约定不兼容；需要 NIfTI RAS / mm")
                actors = vtk_loader.load_coverage_actors(result["files"]["bone_coverage"])
                self.coverage_actors = actors
                self.metrics = result["metrics"]
                self.coverage_manifest = manifest
                self.thickness_views.load(result["files"])
                self.display_settings.coverage_check.setChecked(True)
                self.cartilage_check.setChecked(False)
            self.rebuild_scene()
            if operation in {"segmentation", "analysis"}:
                self.view_grid.ren_3d.ResetCamera()
            self.view_grid.ren_3d.ResetCameraClippingRange()
            self.view_grid.vtk_widget.GetRenderWindow().Render()
            self.seg_modify_dialog.set_has_segmentation(True)
            self.pending = False
            self.task_id = None
            self.status_text = {
                "segmentation": "分割已显示，可继续配准",
                "registration": "配准完成：紫色为模板软骨参考，可调整叠加不透明度",
                "morphometry": "计算完成：绿色为软骨覆盖，灰色为其余骨面",
                "analysis": "全流程完成：分割、配准、指标及模型已加载，可点击“指标结果”查看",
            }[result["operation"]]
            self.on_phase(5, self.status_text)
            if operation in {"morphometry", "analysis"}:
                self.thickness_views.show()
        except Exception as exc:
            self.on_failed(str(exc))

    def rebuild_scene(self):
        self.view_grid.ren_3d.RemoveAllViewProps()
        for actor in (list(self.subject_actors.values()) + list(self.coverage_actors.values())
                      + list(self.template_3d_actors.values())):
            self.view_grid.ren_3d.AddActor(actor)
        self.render_surface()

    def clear_template_overlay(self):
        for actor in self.template_3d_actors.values():
            self.view_grid.ren_3d.RemoveActor(actor)
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
        self.display_settings.patient_check.setChecked(True)
        self.update_patient_overlay()

    def update_patient_overlay(self, *_):
        opacity = self.display_settings.patient_opacity.value() / 100
        self.display_settings.patient_opacity_text.setText(f"{self.display_settings.patient_opacity.value()}%")
        for actor in self.patient_overlays.values():
            actor.SetVisibility(self.display_settings.patient_check.isChecked())
            actor.GetProperty().SetOpacity(opacity)
        for key in self.slice_stacks:
            self.view_grid.widgets[key].GetRenderWindow().Render()

    def load_template_overlay(self, path):
        volume = vtk_loader.load_volume(path, self.current_volume, labels=True)
        overlays = vtk_loader.create_template_overlays(volume, self.slice_actors)
        actors_3d = vtk_loader.create_template_cartilage_actors(volume)
        self.clear_template_overlay()
        self.template_3d_actors = actors_3d
        self.template_overlays = overlays
        for key, actor in overlays.items():
            self.slice_stacks[key].AddImage(actor)
        self.display_settings.template_check.setChecked(True)
        self.display_settings.template_3d_check.setChecked(True)
        self.update_template_overlay()
        self.rebuild_scene()
        if not self.subject_actors and not self.coverage_actors:
            self.view_grid.ren_3d.ResetCamera()
        self.view_grid.ren_3d.ResetCameraClippingRange()
        self.view_grid.vtk_widget.GetRenderWindow().Render()

    def update_template_overlay(self, *_):
        opacity = self.display_settings.template_opacity.value() / 100
        self.display_settings.template_opacity_text.setText(f"{self.display_settings.template_opacity.value()}%")
        for key, actor in self.template_overlays.items():
            actor.SetVisibility(self.display_settings.template_check.isChecked())
            actor.GetProperty().SetOpacity(opacity)
        for key in self.slice_stacks:
            self.view_grid.widgets[key].GetRenderWindow().Render()

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
        opacity = self.display_settings.template_3d_opacity.value() / 100
        self.display_settings.template_3d_opacity_text.setText(f"{self.display_settings.template_3d_opacity.value()}%")
        for actor in self.template_3d_actors.values():
            actor.SetVisibility(self.display_settings.template_3d_check.isChecked())
            actor.GetProperty().SetOpacity(opacity)
        analysis = bool(self.coverage_actors) and self.display_settings.coverage_check.isChecked()
        self.display_settings.legend.setVisible(analysis)
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
        if hasattr(self, "view_grid"):
            self.view_grid.vtk_widget.GetRenderWindow().Render()

    def default_back(self):
        self.display_settings.patient_check.setChecked(True)
        self.display_settings.patient_opacity.setValue(40)
        self.reset_slice_positions()
        self.selected_labels, self.opacity_labels = [True]*5, [70]*5
        self.seg_modify_dialog.set_settings(self.selected_labels, self.opacity_labels)
        self.display_settings.coverage_check.setChecked(True)
        self.cartilage_check.setChecked(False)
        self.display_settings.template_check.setChecked(True)
        self.display_settings.template_opacity.setValue(40)
        self.display_settings.template_3d_check.setChecked(True)
        self.display_settings.template_3d_opacity.setValue(35)
        self.render_surface()

    def show_metrics(self):
        if self.metrics is None:
            return
        dialog = MetricsDialog(self.metrics, self)
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
        self.progress_panel.pipeline_label.setText(self.status_text)
        self.update_actions()
        if self.closing:
            QTimer.singleShot(0, self.close)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.initialized:
            for widget in self.view_grid.widgets.values():
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
        for widget in self.view_grid.widgets.values():
            widget.Finalize()
        self.thickness_views.clear()
        event.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    ##添加应用图标
    icon_path = Path(__file__).resolve().parent / "assets" / "app_icon.ico"
    app.setWindowIcon(QIcon(str(icon_path)))

    window = NiftiSurfaceViewer()
    window.setWindowTitle("膝关节 MRI：形态分析与软骨缺损")
    window.resize(1200, 850)
    window.show()
    sys.exit(app.exec_())

