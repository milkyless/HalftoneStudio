"""驗證：PNG 以 1-bit 輸出，且與計算結果逐像素相同。"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from halftone_studio.core import HalftoneParams, halftone          # noqa: E402
from halftone_studio.image_io import save_image                     # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs"
OUT.mkdir(exist_ok=True)

yy, xx = np.mgrid[0:2000, 0:3000]
gray = (128 + 100 * np.sin(xx / 37.0) * np.cos(yy / 53.0)).clip(0, 255)
gray = gray.astype(np.uint8)

result = halftone(gray, HalftoneParams())
print("半調結果的灰階值:", np.unique(result), "（應只有 0 與 255）")

png_path = OUT / "t1bit.png"
jpg_path = OUT / "t1bit.jpg"

t = time.perf_counter()
save_image(result, str(png_path))
t_png = time.perf_counter() - t

# 對照：原本的 8 位元灰階 PNG
from PIL import Image as _I                                            # noqa: E402
big_path = OUT / "t8bit.png"
_I.fromarray(result, mode="L").save(big_path, format="PNG", optimize=True)

t = time.perf_counter()
save_image(result, str(jpg_path))
t_jpg = time.perf_counter() - t

im = Image.open(png_path)
back = np.array(im.convert("L"))

print()
print("PNG 模式:      ", im.mode)
print("PNG 讀回灰階值:", np.unique(back))
print("與計算結果相同:", np.array_equal(back, result))
print("PNG 中繼資料:  ", len(im.info), "（應為 0）")

kb = lambda p: os.path.getsize(p) / 1024                           # noqa: E731
print()
print(f"PNG 1-bit:  {kb(png_path):8.0f} KB   寫入 {t_png:.2f} 秒")
print(f"PNG 8-bit:  {kb(big_path):8.0f} KB   （對照）")
print(f"壓縮比:     {kb(big_path)/max(kb(png_path), 0.01):.1f} 倍")
print(f"JPEG 100:   {kb(jpg_path):8.0f} KB   寫入 {t_jpg:.2f} 秒")

ok = im.mode == "1" and np.array_equal(back, result) and len(im.info) == 0
print()
print("結果:", "通過" if ok else "失敗")

for p in (png_path, jpg_path, big_path):
    p.unlink(missing_ok=True)

sys.exit(0 if ok else 1)
