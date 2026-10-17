"""參數控制面板的共用小工具。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

__all__ = ["SliderSpin", "InkRange", "build_group", "Lbl"]


def Lbl(text: str) -> QLabel:
    label = QLabel(text)
    label.setMinimumWidth(96)
    return label


class SliderSpin(QWidget):
    """滑桿 + 數值微調框，兩者同步。

    拖動滑桿時只發出 changed（含拖動中），供預覽即時更新；
    放開時才發出 committed，供耗時操作使用。
    """

    changed = Signal(float)
    committed = Signal(float)

    def __init__(self, minimum: float, maximum: float, value: float,
                 decimals: int = 2, step: float = 1.0,
                 suffix: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._decimals = decimals

        # 先建立 spin（_to_slider 依賴它的範圍），再設定滑桿位置
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step)
        self.spin.setRange(minimum, maximum)
        self.spin.setValue(value)
        self.spin.setSuffix(suffix)
        self.spin.setKeyboardTracking(False)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(1000)
        self.slider.setValue(self._to_slider(value))

        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin, 0)

    def _to_slider(self, value: float) -> int:
        lo = self.spin.minimum()
        hi = self.spin.maximum()
        if hi <= lo:
            return 0
        return int(round((value - lo) / (hi - lo) * 1000))

    def _from_slider(self, pos: int) -> float:
        lo = self.spin.minimum()
        hi = self.spin.maximum()
        value = lo + (hi - lo) * (pos / 1000.0)
        return round(value, self._decimals)

    def _on_slider(self, pos: int) -> None:
        value = self._from_slider(pos)
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)
        self.changed.emit(value)

    def _on_spin(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(self._to_slider(value))
        self.slider.blockSignals(False)
        self.changed.emit(value)

    # 放開滑桿或結束編輯時才觸發
    def notify_committed(self) -> None:
        self.committed.emit(self.spin.value())

    def value(self) -> float:
        return float(self.spin.value())

    def set_value(self, value: float) -> None:
        self.spin.setValue(value)


class _DualTrack(QWidget):
    """雙把手滑桿本體。Qt 沒有現成的雙把手 QSlider，只能自己畫。"""

    changed = Signal(float, float)      # 下限, 上限
    committed = Signal(float, float)

    TRACK_H = 8
    HANDLE_W = 13

    def __init__(self, minimum: float = 0.0, maximum: float = 1.0,
                 lo: float = 0.0, hi: float = 1.0,
                 decimals: int = 3,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min = float(minimum)
        self._max = float(maximum)
        self._dec = decimals
        self._lo = float(lo)
        self._hi = float(hi)
        self._drag: int | None = None      # 0 = 下限把手, 1 = 上限把手

        self.setObjectName("dualTrack")
        self.setMinimumHeight(self.TRACK_H + 14)
        self.setMouseTracking(True)

    # ── 值 ────────────────────────────────────────────────
    def _span(self) -> float:
        return max(1e-9, self._max - self._min)

    def _x_of(self, value: float) -> float:
        return (value - self._min) / self._span() * self.width()

    def _value_at(self, x: float) -> float:
        f = max(0.0, min(1.0, x / max(1.0, self.width())))
        return round(self._min + f * self._span(), self._dec)

    def values(self) -> tuple[float, float]:
        return self._lo, self._hi

    def set_values(self, lo: float, hi: float, emit: bool = False) -> None:
        lo = max(self._min, min(self._max, float(lo)))
        hi = max(self._min, min(self._max, float(hi)))
        lo, hi = min(lo, hi), max(lo, hi)
        if (lo, hi) == (self._lo, self._hi):
            return
        self._lo, self._hi = lo, hi
        self.update()
        if emit:
            self.changed.emit(lo, hi)

    # ── 互動 ──────────────────────────────────────────────
    def _handle_rect(self, index: int) -> QRectF:
        x = self._x_of(self._lo if index == 0 else self._hi)
        w = float(self.HANDLE_W)
        return QRectF(x - w / 2.0, 4.0, w, float(self.TRACK_H + 10))

    def _hit_handle(self, x: float, y: float) -> int | None:
        pt = QPointF(x, y)
        for i in (0, 1):
            if self._handle_rect(i).adjusted(-3, -3, 3, 3).contains(pt):
                return i
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        x, y = event.position().x(), event.position().y()
        hit = self._hit_handle(x, y)
        # 按在把手上就拖該把手，否則抓離得較近的那個
        self._drag = hit if hit is not None else (
            0 if abs(x - self._x_of(self._lo)) <= abs(x - self._x_of(self._hi))
            else 1)
        self._apply(self._drag, x)
        self.setCursor(Qt.SizeHorCursor)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        x, y = event.position().x(), event.position().y()
        if self._drag is None:
            self.setCursor(Qt.SizeHorCursor
                           if self._hit_handle(x, y) is not None
                           else Qt.ArrowCursor)
            return
        self._apply(self._drag, x)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None:
            self._drag = None
            self.setCursor(Qt.ArrowCursor)
            self.committed.emit(self._lo, self._hi)
        event.accept()

    def _apply(self, index: int, x: float) -> None:
        v = self._value_at(x)
        lo, hi = self._lo, self._hi
        if index == 0:
            lo = min(v, hi)          # 下限不可超過上限
        else:
            hi = max(v, lo)          # 上限不可低於下限
        if (lo, hi) == (self._lo, self._hi):
            return
        self._lo, self._hi = lo, hi
        self.update()
        self.changed.emit(lo, hi)

    # ── 繪製 ──────────────────────────────────────────────
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        h = float(self.TRACK_H)
        y = float(self.height()) / 2.0 - h / 2.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 224, 236))
        p.drawRoundedRect(QRectF(0.0, y, float(self.width()), h), h / 2, h / 2)

        x0, x1 = self._x_of(self._lo), self._x_of(self._hi)
        p.setBrush(QColor(255, 122, 175))
        p.drawRoundedRect(QRectF(x0, y, max(1.0, x1 - x0), h), h / 2, h / 2)

        p.setPen(QPen(QColor(184, 57, 111), 1.4))
        p.setBrush(QColor(255, 255, 255))
        for i in (0, 1):
            p.drawRoundedRect(self._handle_rect(i), 3.0, 3.0)
        p.end()


class InkRange(QWidget):
    """「墨點大小範圍」控制項：0% 紙白 ~ 100% 完全密實填充。"""

    changed = Signal(float, float)
    committed = Signal(float, float)

    def __init__(self, lo: float = 0.0, hi: float = 1.0,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.spin_lo = QDoubleSpinBox()
        self.spin_hi = QDoubleSpinBox()
        for sp, v in ((self.spin_lo, lo), (self.spin_hi, hi)):
            sp.setDecimals(1)
            sp.setSingleStep(1.0)
            sp.setRange(0.0, 100.0)
            sp.setValue(v * 100.0)
            sp.setSuffix(" %")
            sp.setKeyboardTracking(False)

        self.track = _DualTrack(0.0, 100.0, lo * 100.0, hi * 100.0, 1)
        self.track.changed.connect(self._on_track)
        self.spin_lo.valueChanged.connect(self._on_spin)
        self.spin_hi.valueChanged.connect(self._on_spin)

        # 上下排列：控制面板寬度有限，兩個微調框與標籤並排會把
        # 軌道擠成零寬度，等於看不到把手。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(3)
        outer.addWidget(self.track, 0)

        nums = QHBoxLayout()
        nums.setContentsMargins(0, 0, 0, 0)
        nums.setSpacing(6)
        nums.addStretch(1)
        nums.addWidget(self.spin_lo, 0)
        nums.addWidget(self.spin_hi, 0)
        outer.addLayout(nums, 0)

    def _on_track(self, lo: float, hi: float) -> None:
        for sp, v in ((self.spin_lo, lo), (self.spin_hi, hi)):
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self.changed.emit(lo / 100.0, hi / 100.0)

    def _on_spin(self, _v: float) -> None:
        lo = min(self.spin_lo.value(), self.spin_hi.value())
        hi = max(self.spin_lo.value(), self.spin_hi.value())
        for sp, v in ((self.spin_lo, lo), (self.spin_hi, hi)):
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self.track.set_values(lo, hi)
        self.changed.emit(lo / 100.0, hi / 100.0)

    def notify_committed(self) -> None:
        self.track.committed.emit(*self.track.values())

    def values(self) -> tuple[float, float]:
        return self.spin_lo.value() / 100.0, self.spin_hi.value() / 100.0

    def set_values(self, lo: float, hi: float) -> None:
        for sp, v in ((self.spin_lo, lo * 100.0), (self.spin_hi, hi * 100.0)):
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self.track.set_values(lo * 100.0, hi * 100.0)


def build_group(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setSpacing(6)
    return box, layout


def add_row(layout: QVBoxLayout, label: str, widget: QWidget) -> None:
    row = QHBoxLayout()
    row.addWidget(Lbl(label))
    row.addWidget(widget, 1)
    layout.addLayout(row)
