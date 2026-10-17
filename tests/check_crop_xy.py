"""驗證：點擊總覽預覽得到的座標，與實際高亮的裁切位置一致。

背景問題：總覽顯示的是縮圖（長邊上限 PREVIEW_MAX_EDGE），
但裁切框與細節窗格都用全解析度座標。若直接沿用縮圖座標，
24MP 影像會有 23% 以上的定位誤差 —— 點右下角結果落在全圖 23% 處。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from halftone_studio.image_io import PREVIEW_MAX_EDGE                # noqa: E402


print("=== 座標換算驗證 ===\n")


def convert(px, py, off, shown_scale, disp_w, disp_h, full_w, full_h):
    """複製 ImageView.crop_to_image 的換算邏輯。"""
    disp_x = (px - off[0]) / shown_scale
    disp_y = (py - off[1]) / shown_scale
    return (int(disp_x * full_w / disp_w), int(disp_y * full_h / disp_h))


ok = True
for full_w, full_h in ((6000, 4000), (4000, 3000), (2400, 1600)):
    scale = min(PREVIEW_MAX_EDGE / full_w, PREVIEW_MAX_EDGE / full_h, 1.0)
    pw = int(full_w * scale)
    ph = int(full_h * scale)

    # 視窗比縮圖大 -> 有置中偏移
    vw, vh = 900, 700
    off = ((vw - pw) // 2, (vh - ph) // 2)
    shown = 1.0   # fit 模式下顯示的就是縮圖本身

    # 測試點：縮圖上的 25% / 50% / 75% 位置
    for frac in (0.25, 0.5, 0.75):
        dx, dy = int(pw * frac), int(ph * frac)
        px, py = off[0] + dx, off[1] + dy
        got = convert(px, py, off, shown, pw, ph, full_w, full_h)
        want = (full_w * frac, full_h * frac)
        err = max(abs(got[0] - want[0]) / want[0],
                  abs(got[1] - want[1]) / want[1]) * 100
        good = err < 1.0
        ok &= good
        print(f"  {full_w}x{full_h} 縮圖{pw}x{ph} "
              f"點 {frac:.0%} -> ({got[0]}, {got[1]}) "
              f"應為 ({int(want[0])}, {int(want[1])}) "
              f"誤差 {err:.2f}%  {'OK' if good else 'FAIL'}")

print()
print("結果:", "通過" if ok else "失敗")
sys.exit(0 if ok else 1)
