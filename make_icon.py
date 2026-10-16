"""產生應用程式圖示（.ico）。

以粉嫩風格繪製：粉色底加上黑墨網點，呼應程式的半調主題。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

from halftone_studio.core import DOT_ORGANIC, HalftoneParams, halftone  # noqa: E402

OUT = "docs/halftone.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def make_icon() -> None:
    # 以粉紅色漸層為底
    size = 512
    yy, xx = np.mgrid[0:size, 0:size]
    t = (xx + yy) / (2.0 * size)
    r = np.clip(255 - 20 * t, 0, 255)
    g = np.clip(238 - 70 * t, 0, 255)
    b = np.clip(245 - 25 * t, 0, 255)
    bg = np.dstack([r, g, b]).astype(np.uint8)

    # 疊上半調網點：由左上亮到右下暗，形成漸層
    ramp = np.clip(1.15 - 1.35 * t, 0.0, 1.0)
    gray = ramp.astype(np.float32)
    params = HalftoneParams(dot_shape=DOT_ORGANIC, stochastic=0.12,
                            frequency=26, resolution=170,
                            min_dot=0.0, max_dot=1.0, dot_gain=0.0,
                            shape_amount=0.35, grain_scale=1.0)
    dots = halftone(gray, params).astype(np.float32) / 255.0

    # 網點為黑，與粉紅底結合
    out = (bg.astype(np.float32) * dots[:, :, None]).astype(np.uint8)

    img = Image.fromarray(out, mode="RGB")

    # 圓角，讓圖示在工作列上更俐落
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (8, 8, size - 8, size - 8), radius=96, fill=255)
    img.putalpha(mask)

    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"已產生圖示 {OUT}")
    for s in SIZES:
        print(f"  {s}x{s}")


if __name__ == "__main__":
    make_icon()
