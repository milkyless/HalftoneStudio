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
from PySide6.QtGui import QImage, QMouseEvent                          # noqa: E402
from PySide6.QtWidgets import (                                     # noqa: E402
    QApplication, QPushButton, QScrollArea, QSplitter,
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

print("\n=== 5b. 右下角嚴格角對角錨定 ===")
check("MARGIN 為 0（角對角嚴格對齊）", DetailWindow.MARGIN == 0,
      f"（MARGIN={DetailWindow.MARGIN}）")


def gap():
    v_g = v.mapToGlobal(QPoint(v.width(), v.height()))
    d_g = dw.mapToGlobal(QPoint(dw.width(), dw.height()))
    return v_g.x() - d_g.x(), v_g.y() - d_g.y()


dw._offset = QPoint(0, 0)
dw.reanchor()
app.processEvents()
g = gap()
check("無偏移時右下角完全重合（誤差 <=1px）",
      abs(g[0]) <= 1 and abs(g[1]) <= 1,
      f"（右緣差 {g[0]}px、下緣差 {g[1]}px）")

# 有偏移時應維持該偏移
off_x, off_y = dw._offset.x(), dw._offset.y()
for mv in ((80, 60), (-140, 100), (0, -90)):
    win.move(win.pos().x() + mv[0], win.pos().y() + mv[1])
    app.processEvents()
    g = gap()
    check(f"主視窗移動 {mv} 後維持對齊",
          abs(g[0] + off_x) <= 2 and abs(g[1] + off_y) <= 2,
          f"（右緣差 {g[0]}、下緣差 {g[1]}，應為 {-off_x}、{-off_y}）")

win.resize(1300, 800)
app.processEvents()
g = gap()
check("主視窗縮放後維持對齊",
      abs(g[0] + off_x) <= 2 and abs(g[1] + off_y) <= 2,
      f"（右緣差 {g[0]}、下緣差 {g[1]}，應為 {-off_x}、{-off_y}）")
win.resize(1500, 940)
app.processEvents()

print("\n=== 5c. 不被蓋到後面 / 不超出主視窗 ===")
check("浮動視窗是主視窗的子視窗（Qt.Tool 才能維持置頂）",
      dw.parentWidget() is win, f"（parent={dw.parentWidget()}）")

# 拖曳分隔線改變預覽區大小也要跟著錨定
dw._offset = QPoint(0, 0)
dw.reanchor()
splits = win.findChildren(QSplitter)
split = splits[0] if splits else None
check("找得到分隔線控件", split is not None)
before_w = v.width()
if split is not None:
    split.setSizes([700, 800])
    app.processEvents()
    g = gap()
    check("拖曳分隔線改變預覽寬度後仍錨定",
          v.width() != before_w and abs(g[0]) <= 1 and abs(g[1]) <= 1,
          f"（預覽寬 {before_w} -> {v.width()}，右緣差 {g[0]}、"
          f"下緣差 {g[1]}）")
    split.setSizes([1000, 500])
    app.processEvents()

win.raise_()
win.activateWindow()
app.processEvents()
check("主視窗置前後浮動視窗仍可見", dw.isVisible())


def report_bounds():
    """回報浮動視窗與主視窗的邊界，並判斷四邊是否都在範圍內。"""
    mw = win.mapToGlobal(QPoint(0, 0))
    dg = dw.mapToGlobal(QPoint(0, 0))
    dg_r = dg.x() + dw.width() - 1
    dg_b = dg.y() + dw.height() - 1
    mw_r = mw.x() + win.width() - 1
    mw_b = mw.y() + win.height() - 1
    inside = (dg.x() >= mw.x() and dg.y() >= mw.y()
              and dg_r <= mw_r and dg_b <= mw_b)
    detail = (f"（浮窗 {dg.x()},{dg.y()} ~ {dg_r},{dg_b}；"
              f"主視窗 {mw.x()},{mw.y()} ~ {mw_r},{mw_b}）")
    return inside, detail


dw.resize(5000, 4000)
app.processEvents()
inside, detail = report_bounds()
check("浮動視窗不超出主視窗範圍", inside, detail)

win.resize(700, 480)
app.processEvents()
dw.reanchor()
app.processEvents()
inside, detail = report_bounds()
check("主視窗縮小後浮動視窗仍被夾在範圍內", inside, detail)

# 尺寸上限也不能超過主視窗
dw.resize(5000, 4000)
app.processEvents()
check("浮動視窗最大尺寸受主視窗限制",
      dw.maximumWidth() <= win.width() and dw.maximumHeight() <= win.height(),
      f"（上限 {dw.maximumWidth()}x{dw.maximumHeight()}，"
      f"主視窗 {win.width()}x{win.height()}）")

win.resize(1500, 940)
app.processEvents()
dw.reanchor()
app.processEvents()

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


print("\n=== 2. 點擊選取位置與框線對齊 ===")
win.detail.cmb_size.setCurrentIndex(0)   # 640x480
app.processEvents()
cw, ch = 640, 480

drawn = v.drawn_rect()
check("影像確實繪製在控件內", not drawn.isEmpty(),
      f"（矩形 {drawn.x()},{drawn.y()} {drawn.width()}x{drawn.height()}，"
      f"控件 {v.width()}x{v.height()}）")
check("影像未被控件裁切",
      drawn.width() <= v.width() and drawn.height() <= v.height(),
      f"（影像 {drawn.width()}x{drawn.height()} vs 控件 "
      f"{v.width()}x{v.height()}）")

# 點影像的 75% 位置
px = drawn.left() + int(drawn.width() * 0.75)
py = drawn.top() + int(drawn.height() * 0.75)

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

# ── 框線實際畫出來的位置是否正確 ──────────────────────
# 直接從畫面上找出粉紅框線的像素範圍，比對理論值。


def pink_bbox(img):
    """回傳畫面上粉紅框線的像素範圍 (minx, miny, maxx, maxy)。"""
    im = img.convertToFormat(QImage.Format_RGB32)
    w, h = im.width(), im.height()
    bpl = im.bytesPerLine()
    buf = np.frombuffer(im.constBits(), dtype=np.uint8, count=bpl * h)
    arr = buf.reshape(h, bpl)[:, :w * 4].reshape(h, w, 4)
    r = arr[:, :, 2].astype(np.int16)
    g = arr[:, :, 1].astype(np.int16)
    b = arr[:, :, 0].astype(np.int16)
    mask = ((abs(r - 255) < 40) & (abs(g - 90) < 45)
            & (abs(b - 150) < 45))
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


app.processEvents()
box = win.view._crop
# grab() 回傳的是裝置像素（高 DPI 螢幕為邏輯像素的 2 倍），
# 理論值必須乘上 devicePixelRatio 才可比對。
_dpr = v.grab().devicePixelRatio()
bb = pink_bbox(v.grab().toImage())
fw, fh = full.shape[1], full.shape[0]
exp_x = (drawn.left() + box[0] / fw * drawn.width()) * _dpr
exp_y = (drawn.top() + box[1] / fh * drawn.height()) * _dpr
exp_w = box[2] / fw * drawn.width() * _dpr
exp_h = box[3] / fh * drawn.height() * _dpr

check("總覽上找得到粉紅框線", bb is not None,
      f"（像素範圍 {bb}，DPR={_dpr}）")
if bb:
    minx, miny, maxx, maxy = bb
    ex = (minx + maxx + 1) / 2
    ey = (miny + maxy + 1) / 2
    tx = exp_x + exp_w / 2
    ty = exp_y + exp_h / 2
    dc = max(abs(ex - tx), abs(ey - ty))
    # 框線筆寬 2 邏輯 px，筆畫向兩側各外擴 1px，量到的像素框會比
    # 邏輯矩形大 2px（裝置像素為 2*DPR）。
    pad = 2 * _dpr
    dwid = abs((maxx - minx + 1) - exp_w - pad)
    dhei = abs((maxy - miny + 1) - exp_h - pad)
    check("框線中心與理論位置一致（誤差 <=3px）", dc <= 3,
          f"（畫面中心 {ex:.1f},{ey:.1f}，理論 {tx:.1f},{ty:.1f}，"
          f"差 {dc:.1f}px）")
    check("框線尺寸與理論一致（扣筆寬後誤差 <=4px）",
          dwid <= 4 and dhei <= 4,
          f"（畫面 {maxx-minx+1}x{maxy-miny+1}，"
          f"理論 {exp_w:.1f}+筆寬{pad:.0f}={exp_w+pad:.1f} "
          f"x {exp_h+pad:.1f}）")

# 放大模式下框線仍須正確（QLabel 私自縮放最容易在這裡出錯）
fit_w = drawn.width()
win.view.set_zoom(2.0)
app.processEvents()
d2 = v.drawn_rect()
check("放大 2 倍後影像確實變大", d2.width() >= fit_w * 1.9,
      f"（置合 {fit_w}px -> 放大 {d2.width()}px）")
check("放大後控件長到可捲動範圍（捲軸才會出現）",
      v.minimumWidth() >= d2.width(),
      f"（控件最小寬 {v.minimumWidth()} vs 影像寬 {d2.width()}）")
bb2 = pink_bbox(v.grab().toImage())
check("放大後仍找得到框線", bb2 is not None, f"（像素範圍 {bb2}）")
if bb2:
    # 捲動後可視區只看到影像的一部分，因此框線寬度以「實際繪製
    # 位置換算」為準，不可用置合模式的尺寸。
    rel_x = (d2.left() + box[0] / fw * d2.width()) * _dpr
    rel_w = box[2] / fw * d2.width() * _dpr
    part = max(0.0, (v.grab().toImage().width() - rel_x)) * _dpr
    expect_w = min(rel_w, part) + 2 * _dpr
    got_w = bb2[2] - bb2[0] + 1
    check("放大後框線寬度與繪製位置相符（誤差 <=12px）",
          abs(got_w - expect_w) <= 12,
          f"（畫面 {got_w}px，預期 {expect_w:.0f}px）")
win.view.fit()
app.processEvents()
check("回到置合模式後控件恢復最小尺寸",
      v.minimumWidth() <= 321 and v.minimumHeight() <= 241,
      f"（最小 {v.minimumWidth()}x{v.minimumHeight()}）")

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
