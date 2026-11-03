import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QSplashScreen


def create_splash_pixmap(icon_path):
    """绘制黑橙风格的启动画面。"""
    canvas = QPixmap(480, 300)
    canvas.fill(QColor("#202226"))

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    logo = QPixmap(str(icon_path))
    if not logo.isNull():
        logo = logo.scaled(
            120, 140,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        painter.drawPixmap((480 - logo.width()) // 2, 25, logo)

    painter.setPen(QColor("#F59E42"))
    painter.setFont(QFont("Microsoft YaHei UI", 20, QFont.Bold))
    painter.drawText(
        0, 175, 480, 40,
        Qt.AlignCenter,
        "Knee MRI Studio",
    )

    painter.setPen(QColor("#A6ADB7"))
    painter.setFont(QFont("Microsoft YaHei UI", 10))
    painter.drawText(
        0, 220, 480, 25,
        Qt.AlignCenter,
        "膝关节 MRI · 形态分析与可视化",
    )

    painter.end()
    return canvas


def main():
    app = QApplication(sys.argv)

    icon_path = Path(__file__).resolve().parent / "assets" / "app_icon.png"
    app.setWindowIcon(QIcon(str(icon_path)))

    splash = QSplashScreen(create_splash_pixmap(icon_path))
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    screen = app.primaryScreen()
    if screen is not None:
        splash.move(
            screen.availableGeometry().center()
            - splash.rect().center()
        )

    splash.show()
    splash.showMessage(
        "正在加载可视化组件…",
        Qt.AlignBottom | Qt.AlignHCenter,
        QColor("#E8EAED"),
    )
    app.processEvents()

    # 保持主窗口引用，避免被提前回收
    windows = []

    def load_main_window():
        try:
            # 放在启动画面显示之后，才导入 VTK 和主窗口
            if __package__:
                from .app import NiftiSurfaceViewer
            else:
                from app import NiftiSurfaceViewer

            splash.showMessage(
                "正在初始化界面…",
                Qt.AlignBottom | Qt.AlignHCenter,
                QColor("#E8EAED"),
            )
            app.processEvents()

            window = NiftiSurfaceViewer()
            windows.append(window)
            window.setWindowTitle("膝关节 MRI：形态分析与软骨缺损")
            window.resize(1200, 850)
            window.show()

            splash.finish(window)

        except Exception:
            import traceback
            from PyQt5.QtWidgets import QMessageBox

            error = traceback.format_exc()
            print(error, file=sys.stderr)
            splash.close()
            QMessageBox.critical(None, "启动失败", error)
            app.exit(1)

    QTimer.singleShot(0, load_main_window)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())