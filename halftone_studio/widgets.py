"""參數控制面板的共用小工具。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

__all__ = ["SliderSpin", "build_group", "Lbl"]


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
