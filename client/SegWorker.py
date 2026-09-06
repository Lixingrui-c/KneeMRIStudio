from PyQt5.QtCore import QThread, pyqtSignal
import get_seg

class SegWorker(QThread):
    finished = pyqtSignal(str)   # 成功，返回结果路径
    failed = pyqtSignal(str)     # 失败，返回错误信息

    def __init__(self, file_path, save_dir, server_url):
        super().__init__()
        self.file_path = file_path
        self.save_dir = save_dir
        self.server_url = server_url
        self._is_cancelled = False

    def run(self):
        try:
            # 这里运行耗时操作,不会阻塞 UI
            result_path = get_seg.predict_and_download(
                file_path=self.file_path,
                save_dir=self.save_dir,
                server_url=self.server_url
            )
            if not self._is_cancelled:
                self.finished.emit(result_path)
        except Exception as e:
            if not self._is_cancelled:
                self.failed.emit(str(e))

    def cancel(self):
        self._is_cancelled = True
        # 可以在这里添加请求中断逻辑（如 requests 超时、中断等）