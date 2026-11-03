from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QSize, QPointF
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPolygonF

BUTTON_STYLE = """
QToolButton { background: #34383e; border: 1px solid #41464e;
 border-radius: 6px; padding: 5px; color: #e8eaed; }
QToolButton:hover { background: #3e4249; border-color: #f59e42; }
QToolButton:pressed { background: #4a4034; }
QToolButton:disabled { color: #858b94; background: #292c31; border-color: #363a40; }
"""

def toolbar_icon(key):
    pix=QPixmap(32,32);pix.fill(Qt.transparent)
    p=QPainter(pix);p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#202226" if key=="analysis" else "#e8eaed"),2))
    p.setBrush(Qt.NoBrush)
    if key=="open":
        p.drawRoundedRect(3,9,26,19,2,2);p.drawLine(4,9,4,5);p.drawLine(4,5,14,5);p.drawLine(14,5,18,9)
    elif key=="analysis":
        p.drawPolygon(QPolygonF([QPointF(9,5),QPointF(26,16),QPointF(9,27)]))
    elif key=="metrics":
        p.drawRoundedRect(6,3,21,26,2,2)
        for y in (10,16,22):p.drawLine(11,y,22,y)
    elif key=="thickness":
        for x,y in ((6,22),(14,12),(22,5)):p.drawRoundedRect(x,y,5,28-y,1,1)
    elif key=="display":
        for y,x in ((8,11),(16,22),(24,15)):
            p.drawLine(4,y,28,y);p.drawEllipse(x-3,y-3,6,6)
    else:
        for x in (7,16,25):p.drawEllipse(x-2,14,4,4)
    p.end()
    return QIcon(pix)

def make_toolbar(window, entries):
    toolbar=QtWidgets.QToolBar("常用功能",window)
    toolbar.setMovable(False)
    toolbar.setStyleSheet("QToolBar {background:#292c31;border:0;spacing:8px;padding:5px;}")
    window.addToolBar(toolbar)
    menu=window.menuBar().addMenu("功能")
    more=QtWidgets.QMenu("更多",toolbar)
    actions={}
    window.toolbar_buttons={}
    by_key={item[0]:item for item in entries}
    primary=("open","analysis","metrics","thickness","display")
    for key,title,callback,icon,tip in entries:
        action=QtWidgets.QAction(toolbar_icon(key) if key in primary else window.style().standardIcon(icon),title,window)
        action.setToolTip(tip)
        action.triggered.connect(callback)
        actions[key]=action
        menu.addAction(action)
        if key not in primary:
            more.addAction(action)
    for key in primary:
        button=QtWidgets.QToolButton(toolbar)
        button.setDefaultAction(actions[key])
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(24,24))
        button.setFixedSize(82,66)
        button.setStyleSheet(BUTTON_STYLE + (
            "QToolButton:enabled {background:#f59e42;color:#202226;border-color:#f59e42;} QToolButton:hover:enabled {background:#ffb65f;}" if key=="analysis" else ""))
        toolbar.addWidget(button)
        window.toolbar_buttons[key]=button
    button=QtWidgets.QToolButton(toolbar)
    button.setText("更多")
    button.setIcon(toolbar_icon("more"))
    button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
    button.setMenu(more);button.setFixedSize(70,66);button.setIconSize(QSize(24,24))
    button.setStyleSheet(BUTTON_STYLE)
    toolbar.addWidget(button)
    return actions

class AnalysisDialog(QtWidgets.QDialog):
    def __init__(self, enabled, side, parent=None):
        super().__init__(parent)
        self.operation=None
        self.setWindowTitle("选择分析任务")
        self.setMinimumWidth(480)
        layout=QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("一键运行全流程，或选择其中一个步骤"))
        grid=QtWidgets.QGridLayout()
        layout.addLayout(grid)
        style=QtWidgets.QStyle
        items=[
            ("analysis","一键分析","分割 → 配准 → 指标计算",style.SP_MediaPlay),
            ("segmentation","分割","运行 nnU-Net 分割",style.SP_FileDialogDetailedView),
            ("registration","配准","将模板配准到当前病例",style.SP_BrowserReload),
            ("morphometry","计算指标","计算形态学指标及热力图",style.SP_ComputerIcon),
        ]
        self.buttons={}
        for i,(key,title,detail,icon) in enumerate(items):
            button=QtWidgets.QToolButton(self)
            button.setText(title)
            button.setIcon(self.style().standardIcon(icon))
            button.setIconSize(QSize(32,32))
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setMinimumSize(200,92)
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Fixed)
            button.setStyleSheet(BUTTON_STYLE)
            available=enabled.get(key,False)
            button.setEnabled(available)
            button.setToolTip(detail if available else "请先完成前置步骤，或等待当前任务结束")
            button.clicked.connect(lambda checked=False, operation=key:self.choose(operation))
            grid.addWidget(button,i//2,(i%2)*2,1,2)
            caption=QtWidgets.QLabel(detail);caption.setAlignment(Qt.AlignCenter)
            # Details remain in tooltips to keep the four tiles compact.
            self.buttons[key]=button
        note=QtWidgets.QLabel("单步执行顺序：分割 → 配准 → 计算指标。一键分析会跳过已完成步骤，继续完成剩余任务。")
        note.setWordWrap(True);layout.addWidget(note)
        if side!="right":
            warning=QtWidgets.QLabel("当前为左膝：服务器目前仅配置右膝模板，配准及一键分析需要对应模板；右膝病例请先切换为右膝。")
            warning.setWordWrap(True);layout.addWidget(warning)
        close=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
        close.button(QtWidgets.QDialogButtonBox.Cancel).setText("取消")
        close.rejected.connect(self.reject);layout.addWidget(close)

    def choose(self, operation):
        self.operation=operation
        self.accept()

