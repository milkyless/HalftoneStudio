"""截圖：確認浮動細節視窗與主預覽的外觀（含正體字）。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from halftone_studio.app import MainWindow                          # noqa: E402
from halftone_studio.theme import get_stylesheet                    # noqa: E402

DOCS = ROOT / "docs"
app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(get_stylesheet())

H, W = 3000, 4500
yy, xx = np.mgrid[0:H, 0:W]
c1 = 255 * np.clip(1.4 - np.hypot((xx - W * 0.38) / (W * 0.22),
                                  (yy - H * 0.42) / (H * 0.30)), 0, 1)
c2 = 255 * np.clip(1.4 - np.hypot((xx - W * 0.66) / (W * 0.26),
                                  (yy - H * 0.60) / (H * 0.24)), 0, 1)
base = (200 + 60 * np.sin(xx / 130.0) * np.cos(yy / 170.0))
rgb = np.dstack([np.clip(base, 0, 255),
                 np.clip(base * 0.94 + 20, 0, 255),
                 np.clip(base * 0.88 + 40, 0, 255)])
dark = ((255 - c1) * 0.55 + (255 - c2) * 0.35)[:, :, None]
rgb = np.clip(rgb - dark, 0, 255)
gray = (rgb @ np.array([0.299, 0.587, 0.114])).astype(np.uint8)

win = MainWindow()
win.resize(1700, 1000)
win.show()

small = np.asarray(Image.fromarray(gray).resize(
    (W * 3 // 10, H * 3 // 10), Image.LANCZOS))
win._full_gray = gray
win._rgb = np.repeat(small[:, :, None], 3, axis=2)
win._preview_scale = small.shape[1] / W
win.view.set_full_size(W, H)
win.view.set_rgb(win._rgb)
win.view.fit()
win._refresh_readout()
win.detail.set_gray(gray)
win.act_detail.setChecked(False)
win.act_detail.setChecked(True)
app.processEvents()

# 走真實路徑算一次預覽與細節，否則畫面會是「尚未載入影像」
win.controller.set_gray(small)
win.controller.request(win._params(small.shape[1]))
win._apply_detail()

deadline = time.time() + 120
while time.time() < deadline:
    app.processEvents()
    if not win.controller.busy and not win.detail_ctrl.busy:
        break
    time.sleep(0.01)
for _ in range(40):
    app.processEvents()

# 拉大浮窗以便看清
dw = win.detail_win
dw.resize(720, 520)
app.processEvents()
for _ in range(40):
    app.processEvents()

v_g = win.view.mapToGlobal(QPoint(win.view.width(), win.view.height()))
d_g = dw.mapToGlobal(QPoint(dw.width(), dw.height()))
print("浮窗尺寸:", dw.size().toTuple(),
      " 主視窗:", win.size().toTuple())
print("角對角誤差:  右", v_g.x() - d_g.x(), "px  下",
      v_g.y() - d_g.y(), "px")

shot = DOCS / "ui_float.png"
win.grab().save(str(shot))
print("主視窗截图:", shot, f"{shot.stat().st_size/1024:.0f} KB")

# 浮動視窗是獨立頂層視窗，必須單獨抓，否則主視窗的 grab() 抓不到
dshot = DOCS / "ui_float_win.png"
win.detail_win.grab().save(str(dshot))
print("浮動視窗截图:", dshot, f"{dshot.stat().st_size/1024:.0f} KB")

# 整個畫面：唯一能同時看到兩個視窗、驗證角對角錨定的角度
screen = app.primaryScreen()
if screen is not None:
    sshot = DOCS / "ui_desktop.png"
    screen.grabWindow(0).save(str(sshot))
    print("桌面截图:", sshot, f"{sshot.stat().st_size/1024:.0f} KB")

win.detail_win.close()
win.close()
app.processEvents()
