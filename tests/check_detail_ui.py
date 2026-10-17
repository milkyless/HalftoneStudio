"""整合驗證：浮動細節視窗、點擊定位、背景匯出不凍結介面。

重點對應使用者回報的第 2、3、5 項：
  2. 點擊總覽選取的位置與實際放大的位置不符
  3. 匯出時未回應卡很久
  5. 細節視窗應浮在主預覽右下角、可重疊、可往左上拉伸
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt                          # noqa: E402
from PySide6.QtGui import QMouseEvent                                  # noqa: E402
from PySide6.QtWidgets import (                                     # noqa: E402
    QApplication, QPushButton, QScrollArea,
)

from halftone_studio.app import MainWindow                             # noqa: E402
from halftone_studio.detail import DetailWindow                       # noqa: E402
from halftone_studio.theme import get_stylesheet                       # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "docs"
DOCS.mkdir(exist_ok=True)

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(get_stylesheet())

# 看門狗：任何未預期的模態對話框或死循環都在 180 秒後強制結束，
# 避免測試把終端卡住。
WATCHDOG_SEC = 180
from PySide6.QtCore import QTimer                                     # noqa: E402


def _bail() -> None:
    print(f"\n逾時 {WATCHDOG_SEC} 秒仍未結束，強制中斷（可能有模態對話框）")
    import os
    os._exit(2)


QTimer.singleShot(WATCHDOG_SEC * 1000, _bail)

failures: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{extra}")
    if not cond:
        failures.append(label)


def click(widget, x, y, press=True):
    ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(x, y), QPointF(x, y),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    if press:
        widget.mousePressEvent(ev)
    return ev


def drag(widget, x0, y0, x1, y1):
    click(widget, x0, y0)
    widget.mouseMoveEvent(QMouseEvent(
        QEvent.MouseMove, QPointF(x1, y1), QPointF(x1, y1),
        Qt.NoButton, Qt.LeftButton, Qt.NoModifier))


# ── 準備測試影像（模擬 24MP） ───────────────────────────
FULL_W, FULL_H = 6000, 4000
src = DOCS / "_ui_src.jpg"
yy, xx = np.mgrid[0:FULL_H, 0:FULL_W]
arr = (128 + 90 * np.sin(xx / 190.0) * np.cos(yy / 260.0)).clip(0, 255)
Image.fromarray(arr.astype(np.uint8), mode="L").save(src, quality=90)

win = MainWindow()
win.resize(1500, 940)
win.show()
app.processEvents()

full = np.asarray(Image.open(src).convert("L"))
small = np.asarray(Image.fromarray(full).resize(
    (full.shape[1] * 3 // 10, full.shape[0] * 3 // 10), Image.LANCZOS))
win._full_gray = full
win._rgb = np.repeat(small[:, :, None], 3, axis=2)
win._preview_scale = small.shape[1] / full.shape[1]
win.view.set_full_size(full.shape[1], full.shape[0])
win.view.set_rgb(win._rgb)
win.view.fit()
win.detail.set_gray(full)
app.processEvents()

# 走真實路徑：取消再勾選選單項，觸發定位並顯示浮動視窗
win.act_detail.setChecked(False)
win.act_detail.setChecked(True)
app.processEvents()


print("\n=== 5. 浮動細節視窗 ===")
dw = win.detail_win
check("浮動視窗已顯示", dw.isVisible())
check("是獨立頂層視窗（可疊在主預覽之上）", dw.isWindow())
check("無系統邊框（FramelessWindowHint）",
      bool(dw.windowFlags() & Qt.FramelessWindowHint))
check("置於主視窗之上（Tool 旗標）",
      bool(dw.windowFlags() & Qt.Tool))

v = win.view
v_g = v.mapToGlobal(QPoint(v.width(), v.height()))
d_g = dw.mapToGlobal(QPoint(dw.width(), dw.height()))
gap_x = v_g.x() - d_g.x()
gap_y = v_g.y() - d_g.y()
check("貼近主預覽右下角", 0 <= gap_x <= 60 and 0 <= gap_y <= 60,
      f"（右緣差 {gap_x}px、下緣差 {gap_y}px）")
check("主預覽已佔滿中央區（未被面板切割）",
      v.height() > win.height() * 0.6,
      f"（預覽高 {v.height()} / 視窗高 {win.height()}）")

# 左上角控制點往左上拖曳 => 變大，且右下角固定
before = dw.geometry()
right, bottom = before.right(), before.bottom()
grip = dw.layout().itemAt(0).widget().layout().itemAt(0).widget()
drag(grip, 8, 8, -180, -140)
after = dw.geometry()
check("往左上拖曳可放大",
      after.width() > before.width() + 100
      and after.height() > before.height() + 80,
      f"（{before.width()}x{before.height()} -> "
      f"{after.width()}x{after.height()}）")
check("右下角固定（不會超出主視窗右下方）",
      after.right() == right and after.bottom() == bottom)

pos_before = dw.pos()
win.eventFilter(dw.title, QMouseEvent(
    QEvent.MouseButtonPress, QPointF(40, 10), QPointF(40, 10),
    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
win.eventFilter(dw.title, QMouseEvent(
    QEvent.MouseMove, QPointF(140, 110), QPointF(140, 110),
    Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
check("拖曳標題列可移動視窗", dw.pos() != pos_before,
      f"（{pos_before.x()},{pos_before.y()} -> "
      f"{dw.pos().x()},{dw.pos().y()}）")

print("\n=== 5b. 右下角恆常錨定 ===")
# 拖曳後記下的偏移量（向右下為正，故右下角間距會相應減少）
off_x = dw._offset.x()
off_y = dw._offset.y()
check("拖曳被記成相對錨點的偏移", (off_x, off_y) != (0, 0),
      f"（偏移 {off_x},{off_y}）")

# 錨點間距 12；使用者往右下拖多少，右下角間距就減多少
want_x = DetailWindow.MARGIN - off_x
want_y = DetailWindow.MARGIN - off_y


def gap():
    v_g = v.mapToGlobal(QPoint(v.width(), v.height()))
    d_g = dw.mapToGlobal(QPoint(dw.width(), dw.height()))
    return v_g.x() - d_g.x(), v_g.y() - d_g.y()


# 主視窗移動 -> 浮窗必須同步
for mv in ((80, 60), (-140, 100), (0, -90)):
    win.move(win.pos().x() + mv[0], win.pos().y() + mv[1])
    app.processEvents()
    g = gap()
    check(f"主視窗移動 {mv} 後仍對齊右下角",
          abs(g[0] - want_x) <= 2 and abs(g[1] - want_y) <= 2,
          f"（右緣差 {g[0]}、下緣差 {g[1]}，應為 {want_x}、{want_y}）")

# 主視窗縮放 -> 同樣維持
win.resize(1300, 800)
app.processEvents()
g = gap()
check("主視窗縮放後仍對齊右下角",
      abs(g[0] - want_x) <= 2 and abs(g[1] - want_y) <= 2,
      f"（右緣差 {g[0]}、下緣差 {g[1]}，應為 {want_x}、{want_y}）")
win.resize(1500, 940)
app.processEvents()

# 沒有偏移時應精確貼齊（含 12px 間距）
dw._offset = QPoint(0, 0)
dw.reanchor()
app.processEvents()
g = gap()
check("無偏移時精確貼齊右下角（間距 12px）",
      g[0] == 12 and g[1] == 12,
      f"（右緣差 {g[0]}、下緣差 {g[1]}）")

win._on_detail_close(type("E", (), {"accept": lambda s: None})())
check("關閉鈕可隱藏視窗", not dw.isVisible())
check("選單勾選同步取消", not win.act_detail.isChecked())
win.act_detail.setChecked(True)
app.processEvents()
check("選單可重新叫回視窗", dw.isVisible())

# 內容不應把視窗撐大（否則關閉鈕會被擠出畫面）
dw.resize(640, 470)
app.processEvents()
hint = dw.sizeHint()
check("視窗尺寸不會被內容撐大", dw.width() <= 700 and dw.height() <= 560,
      f"（指定 640x470，sizeHint {hint.width()}x{hint.height()}，"
      f"實際 {dw.width()}x{dw.height()}）")
close_btn = [b for b in dw.findChildren(QPushButton)
             if b.toolTip().startswith("關閉")]
check("關閉鈕存在且在視窗範圍內可見",
      bool(close_btn)
      and 0 <= close_btn[0].x() < dw.width() - close_btn[0].width(),
      f"（鈕位於 x={close_btn[0].x() if close_btn else '?'}，"
      f"鈕寬 {close_btn[0].width() if close_btn else '?'}，"
      f"視窗寬 {dw.width()}）")

# 鈕「存在」不夠，必須真的畫出像素。先前用 U+2715 打叉時位置正確
# 卻整顆空白（字型缺該字形），所以比對標題列底色是否被畫面擾動。
if close_btn:
    b = close_btn[0]
    img = dw.grab().toImage()
    btn_img = b.grab().toImage()
    base = img.pixelColor(b.mapTo(dw, b.rect().topLeft()))
    diff = sum(1 for yy in range(btn_img.height())
               for xx in range(btn_img.width())
               if btn_img.pixelColor(xx, yy) != base)
    check("關閉鈕確實畫出可見筆畫", diff > 20,
          f"（與標題列底色不同的像素 {diff} 個，"
          f"底色 {base.name()}）")


print("\n=== 2. 點擊選取位置 ===")
win.detail.cmb_size.setCurrentIndex(0)   # 640x480
app.processEvents()
cw, ch = 640, 480

pm = v.pixmap()
off = v._pixmap_offset()
px = off[0] + int(pm.width() * 0.75)
py = off[1] + int(pm.height() * 0.75)

full_pos = v.crop_to_image(px, py)
expect = (int(full.shape[1] * 0.75), int(full.shape[0] * 0.75))
err = max(abs(full_pos[0] - expect[0]) / expect[0],
          abs(full_pos[1] - expect[1]) / expect[1]) * 100
check("點擊 75% 位置換算到全解析度", err < 1.5,
      f"（得到 {full_pos}，應為 {expect}，誤差 {err:.2f}%）")

click(v, px, py)
app.processEvents()
cx, cy, gw, gh = win.detail.crop_rect()
center = (cx + gw // 2, cy + gh // 2)
dcx = abs(center[0] - expect[0])
dcy = abs(center[1] - expect[1])
check("細節視窗裁切中心與點擊處一致", dcx < cw and dcy < ch,
      f"（中心 {center}，點擊 {expect}，偏差 {dcx}/{dcy}px，"
      f"裁切 {gw}x{gh}）")
box = win.view._crop
check("總覽上的指示框同步更新", box is not None and box[2] == gw,
      f"（指示框 {box}）")

print("\n=== 3. 匯出不凍結介面 ===")
# 匯出完成會彈模態 QMessageBox，processEvents 會卡在對話框裡等人點，
# 因此測試期間先斷開該處理器，只驗證背景執行緒本身。
win.export_ctrl.done.disconnect(win._on_export_done)
win.export_ctrl.failed.disconnect(win._on_export_failed)

out = DOCS / "_ui_out.png"
t0 = time.perf_counter()
win.export_ctrl.start(full, win._params(), str(out))
ticks = 0
while win.export_ctrl.busy and ticks < 60000:
    app.processEvents()
    ticks += 1
    time.sleep(0.001)
elapsed = time.perf_counter() - t0

check("匯出期間主執行緒持續運作（未凍結）", ticks > 200,
      f"（處理了 {ticks} 個事件迴圈）")
check("匯出成功產生檔案", out.exists())
check("匯出耗時合理", elapsed < 120, f"（{elapsed:.1f} 秒）")
if out.exists():
    im = Image.open(out)
    check("輸出為 1-bit PNG", im.mode == "1",
          f"（模式 {im.mode}，{out.stat().st_size/1024:.0f} KB）")

print("\n=== 4. 預覽區外框 ===")
main_area = [a for a in win.findChildren(QScrollArea)
             if a.widget() is win.view]
check("主預覽捲動區已設為無外框",
      bool(main_area) and main_area[0].frameShape() == QScrollArea.NoFrame)

win.detail_win.close()
win.close()
app.processEvents()
# PIL 開啟的檔案在 Windows 會鎖住，先釋放再刪
try:
    im.close()
except Exception:
    pass
import gc                                                          # noqa: E402
gc.collect()
for f in (src, out):
    try:
        f.unlink(missing_ok=True)
    except OSError:
        pass

print()
if failures:
    print(f"失敗 {len(failures)} 項：")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("全部通過")
sys.exit(0)
