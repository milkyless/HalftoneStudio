"""放大检视增减按钮是否正确显示。

使用者回报「加减调整的按钮显示有误」。此脚本把数值微调框放大
截图并放大，方便肉眼确认箭头形状是否正常。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from halftone_studio.theme import get_stylesheet
from halftone_studio.widgets import SliderSpin


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet(get_stylesheet())

    w = SliderSpin(0.0, 1.0, 0.5, 2, 0.01, "")
    w.resize(320, 44)
    w.show()
    for _ in range(20):
        app.processEvents()

    pm = w.grab()
    pm.save("docs/spinbox.png")
    # 再放大 4 倍，方便确认箭头细节
    pm.scaled(pm.width() * 4, pm.height() * 4).save(
        "docs/spinbox_zoom.png")

    spin = w.spin
    print(f"数值微调框尺寸 {spin.width()}x{spin.height()}")
    print("已存 docs/spinbox.png 与 docs/spinbox_zoom.png（4 倍放大）")
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
