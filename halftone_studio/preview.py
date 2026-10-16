"""背景預覽計算。

大圖的半調計算放在背景執行緒，避免凍結 UI：
主執行緒只負責送出參數，工作完成後再送回結果。

採用 QThreadPool + QRunnable，而非自訂 QThread 事件迴圈：
  - 不需要在 worker 執行緒中手動管理事件迴圈
  - Qt 會自動把結果事件排回主執行緒，投遞行為可預期
  - 執行緒數由 Qt 自動調度
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import (
    QObject, QRunnable, QThreadPool, QTimer, Signal, Slot,
)

from .core import HalftoneParams, halftone

__all__ = ["PreviewController"]


class _Emitter(QObject):
    """供背景執行緒 emit，事件會被排回主執行緒處理。"""

    done = Signal(int, object)
    failed = Signal(int, str)


class _Task(QRunnable):
    """單次半調計算任務。"""

    def __init__(self, emitter: _Emitter, job: int, gray: np.ndarray,
                 params: HalftoneParams,
                 origin: tuple[int, int] = (0, 0),
                 full_shape: tuple[int, int] | None = None) -> None:
        super().__init__()
        self._emitter = emitter
        self._job = job
        self._gray = gray
        self._params = params
        self._origin = origin
        self._full_shape = full_shape

    @Slot()
    def run(self) -> None:
        try:
            result = halftone(self._gray, self._params, self._origin,
                              self._full_shape)
        except Exception as exc:
            self._emitter.failed.emit(self._job, str(exc))
            return
        self._emitter.done.emit(self._job, result)




class PreviewController(QObject):
    """管理預覽計算與請求節流，對 UI 提供單一入口。"""

    ready = Signal(np.ndarray)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        # 只允許一個預覽同時計算，避免快速拖動時排隊過多任務
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

        self._emitter = _Emitter(self)
        self._emitter.done.connect(self._on_done)
        self._emitter.failed.connect(self._on_failed)

        self._gray: np.ndarray | None = None
        self._last_params: HalftoneParams | None = None
        self._job = 0
        self._latest = -1
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def set_gray(self, gray: np.ndarray) -> None:
        self._gray = gray
        # 影像換了，用上次使用的參數重新計算
        if self._last_params is not None:
            self.request(self._last_params)

    def request(self, params: HalftoneParams,
                gray: np.ndarray | None = None,
                origin: tuple[int, int] = (0, 0),
                full_shape: tuple[int, int] | None = None) -> None:
        """送出計算請求，並記住參數供換圖時重用。

        帶入 gray 時會改用該影像；origin 為該影像在整張原圖中
        的左上角座標，full_shape 為整張原圖尺寸，兩者讓裁切
        區塊的網格與整圖完全一致。
        """
        if gray is not None:
            self._gray = gray
        if self._gray is None:
            return

        self._last_params = params
        self._job += 1
        self._latest = self._job

        if not self._busy:
            self._busy = True
            self.busy_changed.emit(True)

        self._pool.start(
            _Task(self._emitter, self._job, self._gray, params,
                  origin, full_shape))

    def _on_done(self, job: int, result: np.ndarray) -> None:
        # 丟棄過期結果，只採用最新一次請求
        if job != self._latest:
            return
        self._set_idle()
        self.ready.emit(result)

    def _on_failed(self, job: int, message: str) -> None:
        if job != self._latest:
            return
        self._set_idle()
        self.failed.emit(message)

    def _set_idle(self) -> None:
        if self._busy:
            self._busy = False
            self.busy_changed.emit(False)

    def shutdown(self) -> None:
        self._pool.clear()
        self._pool.waitForDone(3000)
