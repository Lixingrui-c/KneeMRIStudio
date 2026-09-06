import sys
import os
import time

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QProgressDialog
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtCore import Qt, QSize, QTimer, QElapsedTimer

import vtkmodules.all as vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

import get_seg 
import vtk_loader
import SegWorker



class NiftiSurfaceViewer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        # ---------- UI 布局 ----------
        self.frame = QtWidgets.QFrame()
        main_layout = QtWidgets.QHBoxLayout(self.frame)
        
        # --------- 控制区域 -------
        self.create_menu() #创建菜单
        self.left_widget = QtWidgets.QWidget()
        self.left_layout = QtWidgets.QVBoxLayout(self.left_widget)
        self.create_groupbox() #创建盒子,包含选择区域功能和生成建模功能

        # ---------- 显示区域 ----------
        self.right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QGridLayout(self.right_widget)

        # --------- vtk ----------

        ## -------- 3D分区 --------
        self.vtk_widget = QVTKRenderWindowInteractor(self.right_widget)
        self.ren_3d = vtk.vtkRenderer()
        self.ren_3d.SetBackground(0.1, 0.1, 0.1)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.ren_3d)
        self.iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.iren.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())

        ## -------- z切片 --------
        self.widget_slice_z = QVTKRenderWindowInteractor(self.right_widget)
        self.ren_slice_z = vtk.vtkRenderer()
        self.ren_slice_z.SetBackground(0.1, 0.1, 0.1)
        self.widget_slice_z.GetRenderWindow().AddRenderer(self.ren_slice_z)
        self.iren_z = self.widget_slice_z.GetRenderWindow().GetInteractor()
        self.iren_z.SetInteractorStyle(vtk.vtkInteractorStyleImage())
     
        ## -------- x切片 --------
        self.widget_slice_x = QVTKRenderWindowInteractor(self.right_widget)
        self.ren_slice_x = vtk.vtkRenderer()
        self.ren_slice_x.SetBackground(0.1, 0.1, 0.1)
        self.render_window_x = self.widget_slice_x.GetRenderWindow()
        self.widget_slice_x.GetRenderWindow().AddRenderer(self.ren_slice_x)
        self.iren_x = self.widget_slice_x.GetRenderWindow().GetInteractor()
        self.iren_x.SetInteractorStyle(vtk.vtkInteractorStyleImage())

        ## -------- y切片 --------
        self.widget_slice_y = QVTKRenderWindowInteractor(self.right_widget)
        self.ren_slice_y = vtk.vtkRenderer()
        self.ren_slice_y.SetBackground(0.1, 0.1, 0.1)
        self.render_window_y = self.widget_slice_y.GetRenderWindow()
        self.widget_slice_y.GetRenderWindow().AddRenderer(self.ren_slice_y)
        self.iren_y = self.widget_slice_y.GetRenderWindow().GetInteractor()
        self.iren_y.SetInteractorStyle(vtk.vtkInteractorStyleImage())

        #把vtk窗口加到right_layout里面去
        right_layout.addWidget(self.vtk_widget, 0, 0)
        right_layout.addWidget(self.widget_slice_z, 0, 1)
        right_layout.addWidget(self.widget_slice_x, 1, 0)
        right_layout.addWidget(self.widget_slice_y, 1, 1)


        # ----------添加占位提示文字-----------------
        self.placeholder_actors_3d = []    # 存放3D视图的占位文字
        self.placeholder_actors_slices = [] # 存放三个切片视图的占位文字
        self.add_placeholder_text(self.ren_3d, "请点击分割按钮\n生成3D模型", view_type="3D")
        self.add_placeholder_text(self.ren_slice_x, "矢状面\n请打开 .nii.gz 文件", view_type="slices")
        self.add_placeholder_text(self.ren_slice_y, "冠状面\n请打开 .nii.gz 文件", view_type="slices")
        self.add_placeholder_text(self.ren_slice_z, "横断面\n请打开 .nii.gz 文件", view_type="slices")

        # ---------- 整体布局 ---------------
        main_layout.addWidget(self.left_widget, stretch=30)  
        main_layout.addWidget(self.right_widget, stretch=167)
            
        self.current_volume = None
        self.current_seg_volume = None
        self.current_nii_path = None

        self.setCentralWidget(self.frame)
        self.statusBar().showMessage("就绪 - 请打开 .nii.gz 文件并输入等值面阈值")
        #self.showFullScreen()

    def create_menu(self):
        """创建菜单栏和顶部功能栏。"""
        style = self.style()

        # ---------- 功能动作 ----------
        # 菜单栏和工具栏共享 QAction，统一连接和管理功能。
        self.open_action = QtWidgets.QAction(
            style.standardIcon(QtWidgets.QStyle.SP_DialogOpenButton),
            "打开文件",
            self
        )
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setToolTip("打开 MRI 原始文件（.nii.gz）")
        self.open_action.setStatusTip("打开 MRI 原始文件，显示三个方向的切片")
        self.open_action.triggered.connect(self.open_raw_nii_gz)

        self.seg_action = QtWidgets.QAction(
            style.standardIcon(QtWidgets.QStyle.SP_MediaPlay),
            "分割并显示",
            self
        )
        self.seg_action.setToolTip(
            "分割当前 MRI 并显示 3D 模型；已有分割结果时更新显示"
        )
        self.seg_action.setStatusTip(
            "调用分割服务；已有分割结果时按当前区域和透明度重新显示"
        )
        self.seg_action.triggered.connect(self.execute_surface)

        # 后续实现的分析功能：先显示为禁用状态。
        self.volume_action = QtWidgets.QAction(
            style.standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView),
            "计算体积",
            self
        )
        self.area_action = QtWidgets.QAction(
            style.standardIcon(QtWidgets.QStyle.SP_FileDialogContentsView),
            "表面积",
            self
        )
        self.thickness_action = QtWidgets.QAction(
            style.standardIcon(QtWidgets.QStyle.SP_FileDialogInfoView),
            "软骨厚度",
            self
        )

        for action in (
            self.volume_action,
            self.area_action,
            self.thickness_action,
        ):
            action.setEnabled(False)
            action.setToolTip(f"{action.text()}：待实现")

        self.default_action = QtWidgets.QAction(
            style.standardIcon(QtWidgets.QStyle.SP_BrowserReload),
            "恢复默认",
            self
        )
        self.default_action.setToolTip("恢复默认的区域选择和透明度")
        self.default_action.triggered.connect(self.default_back)

        self.exit_action = QtWidgets.QAction("退出", self)
        self.exit_action.triggered.connect(self.close)

        # ---------- 菜单栏 ----------
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        segmentation_menu = menubar.addMenu("分割")
        segmentation_menu.addAction(self.seg_action)

        analysis_menu = menubar.addMenu("分析")
        analysis_menu.addAction(self.volume_action)
        analysis_menu.addAction(self.area_action)
        analysis_menu.addAction(self.thickness_action)

        view_menu = menubar.addMenu("视图")
        view_menu.addAction(self.default_action)

        # ---------- 顶部功能栏 ----------
        self.top_toolbar = QtWidgets.QToolBar("常用功能", self)
        self.top_toolbar.setObjectName("mainToolbar")
        self.top_toolbar.setMovable(False)
        self.top_toolbar.setFloatable(False)
        self.top_toolbar.setAllowedAreas(Qt.TopToolBarArea)

        # 图标在上，文字在下。
        self.top_toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.top_toolbar.setIconSize(QSize(28, 28))

        self.addToolBar(Qt.TopToolBarArea, self.top_toolbar)

        self.top_toolbar.addAction(self.open_action)
        self.top_toolbar.addSeparator()

        self.top_toolbar.addAction(self.seg_action)
        self.top_toolbar.addSeparator()

        self.top_toolbar.addAction(self.volume_action)
        self.top_toolbar.addAction(self.area_action)
        self.top_toolbar.addAction(self.thickness_action)
        self.top_toolbar.addSeparator()

        self.top_toolbar.addAction(self.default_action)

        # 只设置顶部功能栏样式。
        self.top_toolbar.setStyleSheet("""
            QToolBar {
                background-color: #f5f6f8;
                border: none;
                border-bottom: 1px solid #d8dde5;
                spacing: 6px;
                padding: 6px;
            }

            QToolBar QToolButton {
                min-width: 76px;
                padding: 7px 10px;
                border: 1px solid transparent;
                border-radius: 5px;
                color: #253247;
            }

            QToolBar QToolButton:hover {
                background-color: #e6effb;
                border-color: #c5d8f3;
            }

            QToolBar QToolButton:pressed {
                background-color: #d4e4fa;
            }

            QToolBar QToolButton:disabled {
                color: #a0a7b2;
            }

            QToolBar::separator {
                width: 1px;
                background-color: #d8dde5;
                margin: 5px 8px;
            }
        """)

    def open_raw_nii_gz(self):
        """打开原始的.nii.gz文件并读取到内存"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择 NIfTI 文件", "", "NIfTI 文件 (*.nii.gz);;所有文件 (*)"
        )
        if not file_path:
            return

        self.previous_nii_path = self.current_nii_path  # 保存上一次加载的文件路径
        self.current_nii_path = file_path

        self.statusBar().showMessage(f"正在加载: {os.path.basename(file_path)} ...")
        QtWidgets.QApplication.processEvents()

        if self.current_nii_path is not self.previous_nii_path:
            self.current_seg_volume = None  # 清空之前的分割结果

            reader = vtk.vtkNIFTIImageReader()
            reader.SetFileName(file_path)
            reader.Update()

            self.current_volume = reader.GetOutput()
            if self.current_volume is None:
                self.statusBar().showMessage("加载失败！请检查文件格式")
                return

            scalar_range = self.current_volume.GetScalarRange()
            self.statusBar().showMessage(
                f"已加载: {os.path.basename(file_path)}  数据范围: {scalar_range[0]:.2f} ~ {scalar_range[1]:.2f}"
            )

            if self.current_volume == None:
                self.statusBar().showMessage(
                "你还没加载文件呢")
                return
            
            self.load_slice_views()

    def load_slice_views(self):

        """加载切片视图"""

        self.hide_placeholder_text("slices")

        self.ren_slice_x.RemoveAllViewProps()
        self.ren_slice_y.RemoveAllViewProps()
        self.ren_slice_z.RemoveAllViewProps()
        
        actors = vtk_loader.create_slice_actors(self.current_volume)
       
        self.ren_slice_x.RemoveAllViewProps()
        self.ren_slice_x.AddActor(actors[0])
        self.ren_slice_x.ResetCamera() 
        self.widget_slice_x.GetRenderWindow().Render()

        self.ren_slice_y.RemoveAllViewProps()
        self.ren_slice_y.AddActor(actors[1])
        self.ren_slice_y.ResetCamera() 
        self.widget_slice_y.GetRenderWindow().Render()

        self.ren_slice_z.RemoveAllViewProps()
        self.ren_slice_z.AddActor(actors[2])
        self.ren_slice_z.ResetCamera()
        self.widget_slice_z.GetRenderWindow().Render()



    
    def create_groupbox(self):

        """ 创建控制面板 """

        self.choose_boxes = []
        self.opacity_sliders = []

        group_box = QtWidgets.QGroupBox("选择感兴趣的区域")
        group_box_layout = QtWidgets.QVBoxLayout()

        labels = {1: "股骨", 2:"股骨软骨" , 3: "胫骨", 4: "内侧胫骨软骨", 5: "外侧胫骨软骨"}

        self.selected_labels = [1,1,1,1,1]
        self.opacity_labels = [70,70,70,70,70]

        for idx,name in labels.items():
            
            checkbox = QtWidgets.QCheckBox(name)
            checkbox.setProperty("label value",idx)
            checkbox.setCheckState(True)
            checkbox.stateChanged.connect(self.choosebox_has_changed)
            group_box_layout.addWidget(checkbox)
            self.choose_boxes.append(checkbox)

            slider = QtWidgets.QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setValue(70)
            slider.valueChanged.connect(self.slider_has_changed)
            group_box_layout.addWidget(slider)
            self.opacity_sliders.append(slider)


        group_box.setLayout(group_box_layout)
        self.left_layout.addWidget(group_box)

    def choosebox_has_changed(self):
        """选择显示部件"""
        for cb in self.choose_boxes:
            val = cb.property("label value")
            self.selected_labels[val-1] = cb.isChecked()
        print(self.selected_labels)

    def slider_has_changed(self):

        """改变建模透明度"""

        for idx,slider in enumerate(self.opacity_sliders):    
            self.opacity_labels[idx] = slider.value()
        print(self.opacity_labels)

    def execute_surface(self):

        """下载分割文件并开始执行生成表面"""

        if self.current_volume is None:
            self.statusBar().showMessage("请先加载原始文件")
            return

        # 如果已有分割结果且显示设置未变，直接渲染
        if self.current_seg_volume is not None:
            self.render_surface()
            return
        
        #如果还未加载分割数据，向api获取
        else:

                # 创建无限进度对话框
            self.progress = QProgressDialog(self)
            self.progress.setWindowTitle("MRI 自动分割")
            self.progress.setWindowModality(Qt.WindowModal)
            self.progress.setRange(0, 0)
            self.progress.setMinimumDuration(0)
            self.progress.setMinimumWidth(460)
            self.progress.setAutoClose(False)
            self.progress.setAutoReset(False)

            # 自定义内容标签
            self.progress_label = QtWidgets.QLabel()
            self.progress_label.setTextFormat(Qt.PlainText)
            self.progress_label.setWordWrap(True)
            self.progress_label.setMinimumWidth(400)
            self.progress_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.progress.setLabel(self.progress_label)

            self.progress.setCancelButtonText("取消")
            self.progress.canceled.connect(self.on_seg_cancel)

            # 对话框样式
            self.progress.setStyleSheet("""
                QProgressDialog {
                    background-color: #f7f9fc;
                }

                QLabel {
                    color: #334155;
                    font-family: "Microsoft YaHei";
                    font-size: 13px;
                    padding: 12px 4px;
                }

                QProgressBar {
                    min-height: 10px;
                    max-height: 10px;
                    border: none;
                    border-radius: 5px;
                    background-color: #e2e8f0;
                }

                QProgressBar::chunk {
                    background-color: #3b82f6;
                    border-radius: 5px;
                }

                QPushButton {
                    min-width: 80px;
                    padding: 7px 16px;
                    color: #475569;
                    background-color: white;
                    border: 1px solid #cbd5e1;
                    border-radius: 5px;
                }

                QPushButton:hover {
                    background-color: #eff6ff;
                    border-color: #93c5fd;
                }
            """)

            # 使用实际经过时间计时
            self.seg_elapsed = QElapsedTimer()
            self.seg_elapsed.start()

            self.progress_timer = QTimer(self.progress)
            self.progress_timer.setInterval(1000)
            self.progress_timer.timeout.connect(self.update_seg_progress)

            self.update_seg_progress()
            self.progress_timer.start()
            self.progress.show()

            # 创建工作线程
            self.worker = SegWorker.SegWorker(
                self.current_nii_path,
                "seg_result",
                "http://127.0.0.1:8000"
            )
            self.worker.finished.connect(self.on_seg_finished)
            self.worker.failed.connect(self.on_seg_failed)
            self.worker.start()

    def update_seg_progress(self):
        """更新分割等待信息。"""
        elapsed_seconds = self.seg_elapsed.elapsed() // 1000
        minutes, seconds = divmod(elapsed_seconds, 60)

        file_name = os.path.basename(self.current_nii_path)

        self.progress_label.setText(
            "正在处理膝关节 MRI\n\n"
            f"当前文件：{file_name}\n"
            "处理状态：正在请求分割服务并获取结果\n"
            f"已用时间：{minutes:02d}:{seconds:02d}\n\n"
            "完成后将自动加载分割结果并生成 3D 模型。\n"
        )

    def on_seg_cancel(self):
        """用户点击取消按钮"""
        if hasattr(self, "progress_timer"):
            self.progress_timer.stop()

        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.cancel()
            self.worker.quit()
            self.worker.wait()
        self.progress.close()
        self.statusBar().showMessage("分割已取消")

    def on_seg_finished(self, result_path):
        """分割成功"""
        if hasattr(self, "progress_timer"):
            self.progress_timer.stop()

        self.progress.close()  # 关闭对话框
        self.statusBar().showMessage("分割完成")

        # 加载分割结果
        reader = vtk.vtkNIFTIImageReader()
        reader.SetFileName(result_path)
        reader.Update()
        self.current_seg_volume = reader.GetOutput()
        if self.current_seg_volume is None:
            self.statusBar().showMessage("分割结果加载失败！")
            return

        self.render_surface()

    def on_seg_failed(self, error_msg):
        """分割失败"""
        if hasattr(self, "progress_timer"):
            self.progress_timer.stop()

        self.progress.close()
        self.statusBar().showMessage(f"分割失败: {error_msg}")
        QtWidgets.QMessageBox.critical(self, "错误", f"分割服务出错:\n{error_msg}")

            
    def render_surface(self):

        """根据选择的部位和透明度生成表面"""

        if self.current_seg_volume is None:
            return

        self.hide_placeholder_text("3D")
        self.ren_3d.RemoveAllViewProps()
        
        actors = vtk_loader.create_surface_actors(
            self.current_seg_volume,
            self.selected_labels,
            self.opacity_labels)

        for actor in actors:
            print(len(actors))
            self.ren_3d.AddActor(actor)

        self.ren_3d.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()


    def default_back(self):

        """显示部位和透明度回到默认值"""

        self.selected_labels = [1,1,1,1,1]
        self.opacity_labels = [70,70,70,70,70]
        for i in range(5):
            # checkbox
            self.choose_boxes[i].setChecked(True)
            # slider
            self.opacity_sliders[i].setValue(70)

    def add_placeholder_text(self, renderer, text, view_type="3D"):

        actor = vtk.vtkTextActor()
        actor.SetInput(text)
        prop = actor.GetTextProperty()
        prop.SetFontSize(28)
        prop.SetColor(1, 1, 1)                     # 白色
        prop.SetJustificationToCentered()
        prop.SetVerticalJustificationToCentered()
        prop.SetShadow(True)
        prop.SetShadowOffset(2, -2)
        
        # 设置中文字体（Windows 常用字体路径）
        # 宋体: C:/Windows/Fonts/simsun.ttc
        # 微软雅黑: C:/Windows/Fonts/msyh.ttf
        # 黑体: C:/Windows/Fonts/simhei.ttf
        prop.SetFontFamily(vtk.VTK_FONT_FILE)
        prop.SetFontFile(r"C:/Windows/Fonts/simsun.ttc")   # 选择存在的一种
        
        renderer.AddActor(actor)
        if view_type == "3D":
            self.placeholder_actors_3d.append((actor, renderer))
        else:
            self.placeholder_actors_slices.append((actor, renderer))


    def update_placeholder_positions(self):
        placeholder_actors = self.placeholder_actors_3d + self.placeholder_actors_slices
        for actor, renderer in placeholder_actors:
            size = renderer.GetSize()          # (width, height)
            if size[0] == 0 or size[1] == 0:
                continue
            center_x = size[0] // 2
            center_y = size[1] // 2
            actor.SetDisplayPosition(center_x, center_y)

    def hide_placeholder_text(self, view_type="all"):
        if view_type == "3D" or view_type == "all":
            for actor, renderer in self.placeholder_actors_3d:
                actor.SetVisibility(False)
        if view_type == "slices" or view_type == "all":
            for actor, renderer in self.placeholder_actors_slices:
                actor.SetVisibility(False)

    def showEvent(self, event):
        super().showEvent(event)
        # 初始化所有交互器
        self.iren.Initialize()
        self.iren_x.Initialize()
        self.iren_y.Initialize()
        self.iren_z.Initialize()

        # 更新占位文字位置
        self.update_placeholder_positions()
    
        # 强制渲染所有窗口，让背景色生效
        self.vtk_widget.GetRenderWindow().Render()
        self.widget_slice_x.GetRenderWindow().Render()
        self.widget_slice_y.GetRenderWindow().Render()
        self.widget_slice_z.GetRenderWindow().Render()


    def closeEvent(self, event):

        if hasattr(self, "widget_slice_x"):
            self.widget_slice_x.Finalize()

        if hasattr(self, "widget_slice_y"):
            self.widget_slice_y.Finalize()

        if hasattr(self, "widget_slice_z"):
            self.widget_slice_z.Finalize()

        if hasattr(self, "widget_3d"):
            self.widget_3d.Finalize()

        event.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = NiftiSurfaceViewer()
    window.setWindowTitle("膝关节MRI可视化界面")
    window.resize(900, 700)
    window.show()
    sys.exit(app.exec_())