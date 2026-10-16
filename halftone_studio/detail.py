"""全解析度細節放大窗格。

為什麼需要這個：整圖預覽為了效能一定會縮圖，但網點尺寸是以
「像素」計算的 —— 圖縮小了、網點卻沒縮小，兩者比例完全不同，
預覽與實際產出自然對不上。

本窗格直接取「全解析度影像的指定區域」做半調，結果與匯出的檔案
逐像素相同，因此可以真正檢查網點邊緣是否乾淨、顆粒是否自然。
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

__all__ = ["DetailPane", "CROP_SIZES"]

# 可選的裁切範圍（全解析度像素，寬 x 高）
CROP_SIZES = [(640, 480), (960, 720), (1400, 1050)]

_ZOOMS = ["1:1", "2 倍", "3 倍"]


class DetailPane(QWidget):
    """顯示全解析度影像某個區域的半調結果。"""

    crop_changed = Signal(int, int, int, int)   # x, y, w, h

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._gray: np.ndarray | None = None    # 全解析度灰階
        self._crop = (0, 0, CROP_SIZES[0][0], CROP_SIZES[0][1])
        self._result: np.ndarray | None = None
        self._zoom = 1

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 6)
        root.setSpacing(4)

        # ── 工具列 ──────────────────────────────────────
        bar = QHBoxLayout()
        bar.setSpacing(6)

        title = QLabel("細節放大")
        title.setStyleSheet("font-weight: bold; color: #b8396f;")
        bar.addWidget(title)

        self.cmb_size = QComboBox()
        for w, h in CROP_SIZES:
            self.cmb_size.addItem(f"{w}×{h}", (w, h))
        self.cmb_size.currentIndexChanged.connect(self._on_size)
        bar.addWidget(self.cmb_size)

        self.cmb_zoom = QComboBox()
        self.cmb_zoom.addItems(_ZOOMS)
        self.cmb_zoom.currentIndexChanged.connect(self._on_zoom)
        bar.addWidget(self.cmb_zoom)

        btn_center = QPushButton("置中")
        btn_center.clicked.connect(lambda: self.center())
        bar.addWidget(btn_center)

        bar.addStretch(1)

        self.lbl_info = QLabel("尚未載入影像")
        self.lbl_info.setStyleSheet("color: #a06a86; font-size: 11px;")
        bar.addWidget(self.lbl_info)

        root.addLayout(bar)

        # ── 影像區 ──────────────────────────────────────
        self.lbl = QLabel("尚未載入影像")
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setMinimumHeight(180)
        self.lbl.setStyleSheet(
            "background: #fff0f5; border: 1.5px solid #ffc0d6;"
            "border-radius: 8px; color: #c07a99;")

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.lbl)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignCenter)
        root.addWidget(self.scroll, 1)

    # ── 資料 ────────────────────────────────────────────
    def set_gray(self, gray: np.ndarray | None) -> None:
        self._gray = gray
        self._result = None
        self.center()

    def center(self) -> None:
        if self._gray is None:
            return
        h, w = self._gray.shape
        cw, ch = self._crop[2], self._crop[3]
        cw = min(cw, w)
        ch = min(ch, h)
        x = max(0, (w - cw) // 2)
        y = max(0, (h - ch) // 2)
        self._crop = (x, y, cw, ch)
        self._emit_crop()

    def move_crop(self, x: int, y: int) -> None:
        """把裁切中心移到指定的全解析度座標。"""
        if self._gray is None:
            return
        h, w = self._gray.shape
        cw, ch = self._crop[2], self._crop[3]
        x = int(max(0, min(w - cw, x - cw // 2)))
        y = int(max(0, min(h - ch, y - ch // 2)))
        self._crop = (x, y, cw, ch)
        self._emit_crop()

    def crop_rect(self) -> tuple[int, int, int, int]:
        return self._crop

    def crop_source(self) -> np.ndarray | None:
        """取出裁切區域的全解析度灰階。"""
        if self._gray is None:
            return None
        x, y, w, h = self._crop
        return np.ascontiguousarray(self._gray[y:y + h, x:x + w])

    def _emit_crop(self) -> None:
        x, y, w, h = self._crop
        self.crop_changed.emit(x, y, w, h)
        self._update_info()

    def _update_info(self) -> None:
        if self._gray is None:
            self.lbl_info.setText("尚未載入影像")
            return
        x, y, w, h = self._crop
        H, W = self._gray.shape
        self.lbl_info.setText(
            f"全解析度座標 ({x}, {y})　{w}×{h} px　"
            f"（原圖 {W}×{H}）　縮放 {_ZOOMS[self._zoom]}")

    # ── 顯示 ────────────────────────────────────────────
    def set_result(self, result: np.ndarray) -> None:
        self._result = result
        self._render()

    def _render(self) -> None:
        if self._result is None:
            return
        a = self._result
        img = QImage(a.data, a.shape[1], a.shape[0], a.strides[0],
                     QImage.Format_Grayscale8).copy()
        pm = QPixmap.fromImage(img)
        if self._zoom > 1:
            pm = pm.scaled(pm.width() * self._zoom, pm.height() * self._zoom,
                           Qt.KeepAspectRatio, Qt.FastTransformation)
        self.lbl.setPixmap(pm)
        self.lbl.resize(pm.size())
        self.lbl.setText("")
        self._update_info()

    # ── 事件 ────────────────────────────────────────────
    def _on_size(self, index: int) -> None:
        cw, ch = CROP_SIZES[index]
        self.center()
        self._crop = (self._crop[0], self._crop[1],
                      min(cw, self._crop[2]), min(ch, self._crop[3]))
        self._emit_crop()

    def _on_zoom(self, index: int) -> None:
        self._zoom = index + 1
        self._render()
