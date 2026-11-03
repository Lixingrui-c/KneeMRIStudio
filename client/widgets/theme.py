"""Application chrome only; VTK lookup tables and clinical overlays stay unchanged."""
from PyQt5.QtGui import QColor, QPalette

STYLE = """
QWidget { font-family: "Microsoft YaHei UI"; font-size: 10pt; }
QMainWindow, QDialog { background: #202226; }
QMenuBar, QMenu, QToolBar { background: #292c31; color: #e8eaed; }
QMenuBar::item:selected, QMenu::item:selected { background: #45403a; }
QMenu::item:disabled { color: #858b94; }
QToolTip { color: #e8eaed; background: #34383e; border: 1px solid #f59e42; padding: 5px; }
QGroupBox { border: 1px solid #41464e; border-radius: 5px; margin-top: 14px; padding-top: 7px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #a6adb7; }
QPushButton, QComboBox, QSpinBox, QDoubleSpinBox {
 background: #34383e; color: #e8eaed; border: 1px solid #41464e; border-radius: 4px; padding: 5px 10px;
}
QPushButton:hover, QComboBox:hover { border-color: #f59e42; }
QPushButton:pressed { background: #4a4034; }
QPushButton:disabled { color: #858b94; background: #292c31; }
QPushButton:focus { border-color: #f59e42; }
QLineEdit, QTextEdit, QPlainTextEdit { background: #292c31; color: #e8eaed; border: 1px solid #41464e; }
QTabWidget::pane { border: 1px solid #41464e; }
QTabBar::tab { background: #292c31; color: #a6adb7; padding: 8px 16px; }
QTabBar::tab:selected { color: #f59e42; border-bottom: 2px solid #f59e42; }
QHeaderView::section { background: #34383e; color: #e8eaed; padding: 6px; border: 1px solid #41464e; }
QProgressBar { background: #292c31; border: 1px solid #41464e; border-radius: 4px; color: #e8eaed; text-align: center; }
QProgressBar::chunk { background: #f59e42; border-radius: 3px; }
QSlider::groove:horizontal { height: 4px; background: #41464e; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #f59e42; border-radius: 7px; }
QSlider::handle:horizontal:disabled { background: #646a73; }
QStatusBar { background: #292c31; color: #a6adb7; }
"""

def apply_theme(app):
    if app is None or app.property("kneeDarkOrange"):
        return
    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        QPalette.Window: "#202226", QPalette.WindowText: "#e8eaed",
        QPalette.Base: "#292c31", QPalette.AlternateBase: "#34383e",
        QPalette.Text: "#e8eaed", QPalette.Button: "#34383e",
        QPalette.ButtonText: "#e8eaed", QPalette.Highlight: "#f59e42",
        QPalette.HighlightedText: "#202226", QPalette.ToolTipBase: "#34383e",
        QPalette.ToolTipText: "#e8eaed", QPalette.Link: "#f59e42",
        QPalette.Light: "#51565e", QPalette.Mid: "#41464e", QPalette.Dark: "#191919",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#858b94"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    app.setProperty("kneeDarkOrange", True)
