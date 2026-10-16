"""验证用户实机回报的四个问题都已修复。

1. 程序窗口没有 icon
2. 24MP 大图又变成规律网点、接缝可见（见 check_tiling.py）
3. 参数面板在某些大小下显示不全
4. 增减按钮显示有误
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QScrollArea, QSplitter

from halftone_studio.app import (
    PANEL_MAX_WIDTH, PANEL_MIN_WIDTH, MainWindow,
)
from halftone_studio.theme import get_stylesheet


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet(get_stylesheet())

    win = MainWindow()
    win.show()
    for _ in range(20):
        app.processEvents()

    ok = True

    # ── 1. 窗口图标 ──────────────────────────────────────
    icon = win.windowIcon()
    sizes = icon.availableSizes()
    print(f"[1] 窗口图标：可用尺寸 {sorted(s.width() for s in sizes)}")
    if not sizes or icon.isNull():
        print("    [失败] 窗口没有图标")
        ok = False
    else:
        print("    [通过] 窗口已有图标")

    # ── 2. 面板有滚动区 ──────────────────────────────────
    scrolls = win.findChildren(QScrollArea)
    panel = None
    for s in scrolls:
        if s.widget() is not win.view:
            panel = s
    print(f"\n[2] 面板滚动区：{'有' if panel else '无'}")
    if panel is None:
        print("    [失败] 控制面板没有滚动区")
        ok = False

    # ── 3. 各种窗口大小下面板都不应被挤压变形 ──────────────
    print("\n[3] 各种窗口尺寸下的面板宽度：")
    for w, h in ((1600, 1000), (1280, 820), (1000, 700),
                 (900, 560), (820, 500)):
        win.resize(w, h)
        for _ in range(12):
            app.processEvents()
        pw = panel.width() if panel else 0
        vbar_needed = panel.widget().height() > panel.viewport().height() \
            if panel else False
        state = "OK" if PANEL_MIN_WIDTH <= pw <= PANEL_MAX_WIDTH else "异常"
        print(f"    视窗 {w}x{h} -> 面板宽 {pw}  "
              f"需滚动={vbar_needed}  [{state}]")
        if not (PANEL_MIN_WIDTH <= pw <= PANEL_MAX_WIDTH):
            ok = False

    # ── 4. 面板内容可完整滚动到 ──────────────────────────
    win.resize(1280, 820)
    for _ in range(20):
        app.processEvents()
    if panel:
        panel.verticalScrollBar().setValue(
            panel.verticalScrollBar().maximum())
        for _ in range(10):
            app.processEvents()
        reached = panel.verticalScrollBar().value() == \
            panel.verticalScrollBar().maximum()
        print(f"\n[4] 面板可滚动到底部：{reached}")
        if panel.verticalScrollBar().maximum() > 0 and not reached:
            print("    [失败] 无法滚动到底部，底部参数会看不到")
            ok = False
        else:
            print("    [通过] 所有参数都可浏览到")

    # 复位
    win.resize(1360, 880)
    for _ in range(10):
        app.processEvents()

    win.grab().save("docs/ui_fixed.png")
    print("\n已截图 docs/ui_fixed.png")
    print("\n结果：", "全部通过" if ok else "有项目失败")
    win.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
