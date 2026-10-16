"""粉嫩主題樣式表。

集中管理 QSS，讓介面風格一致且易於調整。
所有介面文字皆為正體中文。
"""
from __future__ import annotations

__all__ = ["STYLESHEET"]

_BASE = """
/* ── 整體底色與文字 ───────────────────────────── */
QWidget {
    background-color: #fff5f8;
    color: #5b3a4a;
    font-family: "Microsoft JhengHei UI", "Microsoft JhengHei",
                 "PingFang TC", "Noto Sans TC", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #fff5f8; }

/* ── 選單列 ──────────────────────────────────── */
QMenuBar {
    background-color: #ffd9e6;
    color: #7a3f57;
    border: none;
    padding: 4px;
}
QMenuBar::item {
    padding: 6px 14px;
    border-radius: 8px;
    background: transparent;
}
QMenuBar::item:selected { background-color: #ffb8d0; color: #5b1f38; }
QMenuBar::item:pressed  { background-color: #ffa8c6; }

QMenu {
    background-color: #ffffff;
    border: 1px solid #ffc0d6;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 26px 8px 20px;
    border-radius: 7px;
    color: #5b3a4a;
}
QMenu::item:selected { background-color: #ffd9e6; color: #8a2450; }
QMenu::separator {
    height: 1px;
    background: #ffd6e5;
    margin: 5px 10px;
}

/* ── 分群框 ──────────────────────────────────── */
QGroupBox {
    background-color: #ffffff;
    border: 1.5px solid #ffc9dc;
    border-radius: 14px;
    margin-top: 16px;
    padding: 14px 12px 12px 12px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 16px;
    padding: 2px 10px;
    color: #d1568c;
    background-color: #ffeaf2;
    border: 1.5px solid #ffc9dc;
    border-radius: 9px;
}

/* ── 按鈕 ────────────────────────────────────── */
QPushButton {
    background-color: #ffd0e2;
    border: 1.5px solid #ffa8c6;
    border-radius: 11px;
    padding: 7px 16px;
    color: #8a2450;
    font-weight: bold;
}
QPushButton:hover     { background-color: #ffb8d0; border-color: #ff8fb8; }
QPushButton:pressed   { background-color: #ffa0c0; color: #6b1839; }
QPushButton:disabled  {
    background-color: #fbe4ec;
    border-color: #f0d3de;
    color: #c9a8b6;
}

/* ── 滑桿 ────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 8px;
    background: #ffdce9;
    border-radius: 4px;
}
QSlider::sub-page:horizontal {
    background: #ff9dc0;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: #ffffff;
    border: 2.5px solid #ff7aad;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 10px;
}
QSlider::handle:horizontal:hover {
    background: #fff0f5;
    border-color: #ff5c9a;
}

/* ── 數值微調框 ──────────────────────────────── */
QDoubleSpinBox, QSpinBox {
    background-color: #ffffff;
    border: 1.5px solid #ffc0d6;
    border-radius: 9px;
    padding: 5px 8px;
    color: #6b3350;
    selection-background-color: #ffb8d0;
}
QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #ff7aad;
    background-color: #fffafc;
}
QDoubleSpinBox::up-button, QSpinBox::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button {
    background-color: #ffd0e2;
    border: none;
    width: 16px;
    border-radius: 5px;
    margin: 2px;
}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {
    background-color: #ffb0cb;
}
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #c94d80;
    width: 0; height: 0;
}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #c94d80;
    width: 0; height: 0;
}

/* ── 下拉選單 ────────────────────────────────── */
QComboBox {
    background-color: #ffffff;
    border: 1.5px solid #ffc0d6;
    border-radius: 10px;
    padding: 6px 12px;
    color: #6b3350;
}
QComboBox:hover { border-color: #ff8fb8; background-color: #fffafc; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #d1568c;
    width: 0; height: 0;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1.5px solid #ffc0d6;
    border-radius: 10px;
    padding: 4px;
    selection-background-color: #ffd0e2;
    selection-color: #8a2450;
    outline: none;
}

/* ── 標籤與勾選框 ────────────────────────────── */
QLabel { color: #6b3a52; }
QCheckBox, QRadioButton { color: #6b3a52; spacing: 8px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 17px; height: 17px;
    border: 1.5px solid #ffa8c6;
    border-radius: 5px;
    background-color: #ffffff;
}
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #ff8fb8;
}

/* ── 狀態列 ──────────────────────────────────── */
QStatusBar {
    background-color: #ffe4ee;
    color: #8a4a68;
    border-top: 1.5px solid #ffc9dc;
}
QStatusBar::item { border: none; }

/* ── 進度條 ──────────────────────────────────── */
QProgressBar {
    background-color: #ffffff;
    border: 1.5px solid #ffc9dc;
    border-radius: 10px;
    height: 14px;
    text-align: center;
    color: #8a2450;
}
QProgressBar::chunk {
    background-color: #ff9dc0;
    border-radius: 7px;
}

/* ── 捲軸 ────────────────────────────────────── */
QScrollBar:vertical {
    background: #fff0f5;
    width: 12px;
    margin: 0;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #ffb0cb;
    border-radius: 6px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: #ff8fb8; }
QScrollBar:horizontal {
    background: #fff0f5;
    height: 12px;
    margin: 0;
    border-radius: 6px;
}
QScrollBar::handle:horizontal {
    background: #ffb0cb;
    border-radius: 6px;
    min-width: 32px;
}
QScrollBar::handle:horizontal:hover { background: #ff8fb8; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }

/* ── 分隔條 ──────────────────────────────────── */
QSplitter::handle { background-color: #ffd9e6; }
QSplitter::handle:horizontal { width: 5px; }
QSplitter::handle:hover { background-color: #ffb0cb; }

/* ── 對話框與工具提示 ────────────────────────── */
QMessageBox { background-color: #fff5f8; }
QMessageBox QPushButton { min-width: 88px; }
QToolTip {
    background-color: #ffeaf2;
    color: #6b1f42;
    border: 1.5px solid #ffa8c6;
    border-radius: 8px;
    padding: 6px 9px;
}

/* ── 影像檢視區 ──────────────────────────────── */
QLabel#imageView {
    background-color: #ffeef4;
    border: 2px dashed #ffc0d6;
    border-radius: 14px;
    color: #c07a99;
    font-size: 15px;
}
"""

STYLESHEET = _BASE
