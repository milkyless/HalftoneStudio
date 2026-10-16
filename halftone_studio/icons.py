"""應用程式圖示。

在執行時用 QPainter 畫出來，不依賴外部 .ico 檔案，
因此打包成單檔 exe 後依然正常顯示。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QLinearGradient, QPainter, QPixmap,
)

__all__ = ["app_icon"]

# 粉嫩配色，与 theme.py 一致
_BG_TOP = QColor(255, 236, 243)
_BG_BOTTOM = QColor(255, 196, 221)
_INK = QColor(90, 30, 55)


def _draw(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    # 圆角粉红底
    grad = QPixmap(size, size)
    gp = QPainter(grad)
    gp.setRenderHint(QPainter.Antialiasing, True)
    gp.setBrush(QBrush(_BG_TOP))
    gp.setPen(Qt.NoPen)
    gp.drawRoundedRect(QRectF(0, 0, size, size), size * 0.19, size * 0.19)
    # 由上到下的渐层
    gp.setCompositionMode(QPainter.CompositionMode_SourceAtop)
    grad_brush = QLinearGradient(0, 0, 0, size)
    grad_brush.setColorAt(0.0, _BG_TOP)
    grad_brush.setColorAt(1.0, _BG_BOTTOM)
    gp.fillRect(0, 0, size, size, QBrush(grad_brush))
    gp.end()
    p.drawPixmap(0, 0, grad)

    # 半调网点：由左上亮到右下暗
    n = 5
    pad = size * 0.14
    usable = size - pad * 2
    step = usable / n

    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(_INK))
    for row in range(n):
        for col in range(n):
            # 斜向渐层，左上最亮
            t = (row + col) / (2.0 * (n - 1))
            tone = 1.0 - t

            cx = pad + (col + 0.5) * step
            cy = pad + (row + 0.5) * step
            # 圆点半径正比於 √暗度（AM 半調原理）
            r = step * 0.5 * math.sqrt(max(0.0, tone))

            if r < 0.6:
                continue
            col_ink = QColor(_INK)
            col_ink.setAlphaF(min(1.0, 0.35 + tone * 0.65))
            p.setBrush(QBrush(col_ink))
            p.drawEllipse(QPointF(cx, cy), r, r)

    p.end()
    return pm


def app_icon() -> QIcon:
    """回傳多尺寸的應用程式圖示。"""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw(s))
    return icon
