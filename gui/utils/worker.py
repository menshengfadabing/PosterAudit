"""后台任务工作器"""

from typing import Callable, Any
from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    """后台任务执行线程"""

    started_signal = Signal()
    finished_signal = Signal(object)
    error_signal = Signal(str)
    progress_signal = Signal(int, str)

    def __init__(self, task: Callable, *args, **kwargs):
        super().__init__()
        self.task = task
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def run(self):
        self.started_signal.emit()
        try:
            if 'progress_callback' not in self.kwargs:
                self.kwargs['progress_callback'] = self.report_progress

            result = self.task(*self.args, **self.kwargs)

            if not self._is_cancelled:
                self.finished_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))

    def report_progress(self, percent: int, message: str = ""):
        self.progress_signal.emit(percent, message)

    def cancel(self):
        self._is_cancelled = True