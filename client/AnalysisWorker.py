import threading

from PyQt5.QtCore import QThread, pyqtSignal

if __package__:
    from . import api_client
else:
    import api_client
# 如果你的接口文件仍叫 get_seg.py，改成：
# import get_seg as api_client


class AnalysisWorker(QThread):
    # 不覆盖 QThread 自带的 finished 信号。
    case_created = pyqtSignal(str)
    task_created = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    result_ready = pyqtSignal(dict)
    failed = pyqtSignal(str)
    waiting_stopped = pyqtSignal()

    def __init__(
        self,
        operation,
        file_path=None,
        knee_side=None,
        case_id=None,
        task_id=None,
        save_dir="cache",
        server_url=api_client.LOCAL_URL,
        parent=None,
    ):
        super().__init__(parent)

        self.operation = operation
        self.file_path = file_path
        self.knee_side = knee_side
        self.case_id = case_id
        self.task_id = task_id
        self.save_dir = save_dir
        self.server_url = server_url

        self._stop_event = threading.Event()

    def stop_waiting(self):
        """停止客户端等待，不取消服务器上的计算。"""
        self._stop_event.set()

    def cancel(self):
        """兼容旧代码的方法名，实际含义仍是停止等待。"""
        self.stop_waiting()

    def _check_stopped(self):
        if self._stop_event.is_set():
            raise InterruptedError("已停止等待")

    def run(self):
        try:
            if self.operation not in api_client.OPERATIONS:
                raise ValueError(f"未知操作：{self.operation}")

            if self.task_id and not self.case_id:
                raise ValueError("恢复查询时需要同时提供 case_id 和 task_id")

            self._check_stopped()

            # 1. 首次使用时上传 MRI。
            if not self.case_id:
                if self.operation not in {"segmentation", "analysis"}:
                    raise ValueError("配准和指标计算需要已有的 case_id")

                if not self.file_path or not self.knee_side:
                    raise ValueError("首次上传需要 MRI 路径和左右膝信息")

                self.status_changed.emit("正在上传 MRI…")

                response = api_client.upload_case(
                    file_path=self.file_path,
                    knee_side=self.knee_side,
                    server_url=self.server_url,
                )

                self.case_id = response["case_id"]

                # 即使用户在上传期间停止等待，也保存已创建的 ID。
                self.case_created.emit(self.case_id)

            self._check_stopped()

            # 2. 没有任务 ID 时启动任务；已有 ID 时只恢复查询。
            if not self.task_id:
                self.status_changed.emit("正在提交任务…")

                response = api_client.start_task(
                    case_id=self.case_id,
                    operation=self.operation,
                    server_url=self.server_url,
                )

                self.task_id = response["task_id"]
                self.task_created.emit(self.task_id)

            self._check_stopped()

            # 3. 查询任务，直到完成、失败或用户停止等待。
            self._wait_for_task()

            # 4. 下载结果；网络和文件操作仍在线程中执行。
            result = self._collect_results()

            self._check_stopped()
            self.result_ready.emit(result)

        except InterruptedError:
            self.waiting_stopped.emit()

        except Exception as exc:
            if self._stop_event.is_set():
                self.waiting_stopped.emit()
            else:
                self.failed.emit(str(exc))

    def _wait_for_task(self):
        stage_names = {
            "segmentation": "分割",
            "registration": "配准",
            "morphometry": "形态学指标计算",
        }

        while True:
            self._check_stopped()

            task = api_client.get_task(
                task_id=self.task_id,
                server_url=self.server_url,
            )

            self._check_stopped()

            # 避免误用其他病例的任务 ID。
            if task.get("case_id") != self.case_id:
                raise RuntimeError("任务所属病例与当前病例不一致")

            status = task.get("status")
            stage = task.get("stage")

            if status == "completed":
                self.status_changed.emit("计算完成，正在获取结果…")
                return

            if status == "failed":
                error = task.get("error") or "服务器未提供错误详情"
                raise RuntimeError(f"服务器任务失败：{error}")

            if status == "queued":
                self.status_changed.emit("任务已提交，正在排队…")

            elif status == "running":
                label = stage_names.get(stage, stage or "处理")
                self.status_changed.emit(f"正在执行{label}…")

            else:
                raise RuntimeError(f"未知任务状态：{status}")

            # 等待两秒；收到 stop_waiting() 时会提前结束等待。
            if self._stop_event.wait(2):
                raise InterruptedError("已停止等待")

    def _collect_results(self):
        result = {
            "case_id": self.case_id,
            "task_id": self.task_id,
            "operation": self.operation,
            "files": {},
            "metrics": None,
        }

        downloads = {
            "segmentation": [
                "segmentation",
            ],
            "registration": [
                "registration",
                "qc",
            ],
            "morphometry": [
                "bone_coverage",
                "coverage_manifest",
                "metrics",
                "compartments",
                "areas",
                "metadata",
            ],
            "analysis": [
                "registration",
                "segmentation",
                "bone_coverage",
                "coverage_manifest",
                "qc",
                "metrics",
                "compartments",
                "areas",
                "metadata",
            ],
        }

        for name in downloads[self.operation]:
            self._check_stopped()
            self.status_changed.emit(f"正在下载结果：{name}")

            path = api_client.download_result(
                case_id=self.case_id,
                name=name,
                save_dir=self.save_dir,
                server_url=self.server_url,
            )
            result["files"][name] = path

        self._check_stopped()

        if self.operation in {"morphometry", "analysis"}:
            result["metrics"] = api_client.get_metrics(
                case_id=self.case_id,
                server_url=self.server_url,
            )

        return result
