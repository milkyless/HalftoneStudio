"""全解析度細節放大窗格。

為什麼需要這個：整圖預覽為了效能一定會縮圖，但網點尺寸是以
「像素」計算的 —— 圖縮小了、網點卻沒縮小，兩者比例完全不同，
預覽與實際產出自然對不上。

本窗格直接取「全解析度影像的指定區域」做半調，結果與匯出的檔案
逐像素相同，因此可以真正檢查網點邊緣是否乾淨、顆粒是否自然。
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor, QImage, QPainter, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

__all__ = ["DetailPane", "DetailWindow", "CROP_SIZES"]

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
        root.addLayout(bar)

        # 座標資訊另起一行。若與工具列同一行，這段文字的最小寬度
        # 會把視窗撐到 1280px 以上，連帶把標題列的關閉鈕擠出畫面。
        self.lbl_info = QLabel("尚未載入影像")
        self.lbl_info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_info.setStyleSheet("color: #a06a86; font-size: 11px;")
        self.lbl_info.setMinimumWidth(0)
        root.addWidget(self.lbl_info)

        # ── 影像區 ──────────────────────────────────────
        self.lbl = QLabel("尚未載入影像")
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setMinimumSize(1, 1)     # 不可省略：見下方說明
        self.lbl.setStyleSheet(
            "background: #fff0f5; border: 1.5px solid #ffc0d6;"
            "border-radius: 8px; color: #c07a99;")

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.lbl)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignCenter)
        # QScrollArea 的最小尺寸預設會吃進內部 widget 的需求。放大後的
        # 標籤可能是 1280x960，若不設下限，整個浮動視窗就會被撐成一樣大。
        # 明確指定下限，讓視窗維持在使用者設定的大小、影像改以捲動顯示。
        self.scroll.setMinimumSize(240, 150)
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


# ── 浮動細節視窗 ────────────────────────────────
class _ResizeGrip(QWidget):
    """左上角的三角控制點：往左上拖曳即可放大視窗。

    一般視窗靠右下角放大，但這是浮在主視窗上的小窗，實務上要往
    左上拉才不會把主畫面推出去 —— 右下角被主視窗邊界擋住。
    因此這個控制點放左上角，拖曳時固定右下角為錨點。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setCursor(Qt.SizeFDiagCursor)
        self.setToolTip("往左上拖曳可放大視窗")
        self._start: tuple | None = None

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(184, 57, 111, 160))
        w, h = self.width(), self.height()
        # 左上角 L 形：兩條對角線段
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(w, 0),
                                 QPointF(0, h)]))
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawPolygon(QPolygonF([QPointF(3, 3), QPointF(w - 3, 3),
                                 QPointF(3, h - 3)]))
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            win = self.window()
            self._start = (event.globalPosition().toPoint(),
                           win.geometry())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start is None or not (event.buttons() & Qt.LeftButton):
            return
        origin_pos, origin_geo = self._start
        win = self.window()
        delta = event.globalPosition().toPoint() - origin_pos

        # 右下角固定，往左上拉 => 尺寸變大、起點往左上移
        right = origin_geo.right()
        bottom = origin_geo.bottom()
        width = min(origin_geo.width() - delta.x(), win.maximumWidth() or 10**6)
        height = min(origin_geo.height() - delta.y(), win.maximumHeight() or 10**6)
        width = max(width, win.minimumWidth())
        height = max(height, win.minimumHeight())
        win.setGeometry(right - width + 1, bottom - height + 1,
                        width, height)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._start = None
        super().mouseReleaseEvent(event)


class DetailWindow(QWidget):
    """浮動的細節放大視窗。

    做成獨立的無邊框視窗而非底部面板，才能疊在主預覽之上，
    不佔用固定版面；使用者可隨時拖到任何位置或關閉。
    """

    def __init__(self, pane: DetailPane,
                 parent: QWidget | None = None) -> None:
        # 必須指定 parent：Qt.Tool 唯有在有父子關係時才會自動維持在
        # 父視窗之上。若傳 None，它就是一般頂層視窗，主視窗一旦被
        # 點選而提到最前面，浮動視窗就會被蓋到後面去。
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMinimumSize(320, 240)
        self.pane = pane
        self._target: QWidget | None = None
        self._offset = QPoint(0, 0)
        self._drag_from: tuple | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        # ── 標題列：左上角控制點 + 可拖曳區 + 關閉鈕 ──
        bar = QWidget()
        bar.setFixedHeight(22)
        bar.setStyleSheet(
            "background: #ffd6e6; border-bottom: 1px solid #f0a8c8;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 2, 0)
        bl.setSpacing(0)
        bl.addWidget(_ResizeGrip(bar))

        self.title = QLabel(" 細節放大（拖曳可移動）")
        self.title.setStyleSheet(
            "color: #8c2a55; font-size: 11px; font-weight: bold;"
            "background: transparent;")
        bl.addWidget(self.title, 1)

        # 用 U+00D7 乘號而非 U+2715 打叉：後者不在 Windows 預設
        # 中文字型裡，會因缺字形而整個鈕畫不出來。
        btn_close = QPushButton("×")
        btn_close.setFixedSize(22, 18)
        btn_close.setCursor(Qt.ArrowCursor)
        btn_close.setToolTip("關閉細節放大視窗")
        btn_close.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " color: #b8396f; font-size: 15px; font-weight: bold;"
            " padding: 0; }"
            "QPushButton:hover { background: #ff7fb5; color: white; }")
        btn_close.clicked.connect(self.hide)
        bl.addWidget(btn_close)

        outer.addWidget(bar)
        outer.addWidget(self.pane, 1)
        self._bar = bar

    # ── 位置 ────────────────────────────────────────────
    # 浮動視窗的右下角恆常錨定在主預覽區的右下角，角對角嚴格對齊
    # （MARGIN = 0）。使用者仍可拖曳移動，移動量會記成相對錨點的
    # 偏移，主視窗移動或縮放時依此偏移重新定位。
    MARGIN = 0

    def _fit_to_parent(self) -> None:
        """限制尺寸不得超出主視窗，避免視窗被拖到畫面外找不回來。"""
        p = self.parentWidget()
        if p is None:
            return
        self.setMaximumSize(max(self.minimumWidth(), p.width()),
                            max(self.minimumHeight(), p.height()))
        if self.width() > p.width():
            self.resize(p.width(), self.height())
        if self.height() > p.height():
            self.resize(self.width(), p.height())

    def anchor_to(self, target: QWidget) -> None:
        """把右下角錨定到目標元件（主預覽區）的右下角。"""
        self._target = target
        self._fit_to_parent()
        self.adjustSize()
        p = self.parentWidget()
        w = min(max(self.sizeHint().width(), self.minimumWidth()),
                720 if p is None else p.width())
        h = min(max(self.sizeHint().height(), self.minimumHeight()),
                520 if p is None else p.height())
        self.resize(w, h)
        self.reanchor()

    def _anchor_local(self) -> QPoint:
        """錨點在目標元件座標系中的位置。"""
        t = getattr(self, "_target", None)
        if t is None:
            return QPoint(0, 0)
        return QPoint(t.width() - self.width() - self.MARGIN,
                      t.height() - self.height() - self.MARGIN)

    def _anchor_global(self) -> QPoint:
        t = getattr(self, "_target", None)
        if t is None:
            return self.pos()
        return t.mapToGlobal(self._anchor_local())

    def _clamp_inside(self, x: int, y: int) -> QPoint:
        """把視窗夾在主視窗範圍內。"""
        p = self.parentWidget()
        if p is None:
            return QPoint(x, y)
        r = QRect(p.mapToGlobal(QPoint(0, 0)), p.size())
        x = max(r.left(), min(x, r.right() - self.width() + 1))
        y = max(r.top(), min(y, r.bottom() - self.height() + 1))
        return QPoint(x, y)

    def reanchor(self) -> None:
        """依目前目標重新定位，保持右下角對齊與使用者的拖曳偏移。"""
        if getattr(self, "_busy_anchor", False):
            return
        t = getattr(self, "_target", None)
        if t is None or not self.isVisible():
            return
        # re-entrancy：_fit_to_parent 可能觸發 resize，而 resize 會再
        # 呼叫這裡；不設旗標會無窮遞迴。
        self._busy_anchor = True
        try:
            # 主視窗可能已縮小，尺寸上限要跟著更新，否則視窗會大到
            # 超出主視窗而找不回來。
            self._fit_to_parent()
            g = self._anchor_global()
            pos = self._clamp_inside(g.x() + self._offset.x(),
                                     g.y() + self._offset.y())
            self.move(pos)
        finally:
            self._busy_anchor = False
        # 主視窗被點選或重繪後，浮動視窗可能被蓋到後面，這裡補一次置前
        self.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # 使用者把視窗拉大超出主視窗時，立刻夾回範圍內
        self.reanchor()

    def drag_begin(self, pos) -> None:
        p = pos.toPoint() if hasattr(pos, "toPoint") else pos
        self._drag_from = (p, self.geometry())

    def drag_move(self, pos) -> None:
        if self._drag_from is None:
            return
        origin, geo = self._drag_from
        cur = pos.toPoint() if hasattr(pos, "toPoint") else pos
        d = cur - origin
        nx, ny = geo.x() + d.x(), geo.y() + d.y()

        # 記成相對錨點的偏移，主視窗移動後才不會被拉回原位
        anchor = self._anchor_global()
        self._offset = QPoint(nx - anchor.x(), ny - anchor.y())
        self.move(nx, ny)

    def drag_end(self) -> None:
        self._drag_from = None
