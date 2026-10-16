"""视觉对比：总览预览 vs 实际产出。

上排 = 应用的总览预览（缩图 + 解析度同步缩放）
下排 = 全解析度产出缩到相同显示尺寸

两者的网点相对密度若一致，肉眼看到的颗粒质感就应该接近。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from halftone_studio.core import DOT_ORGANIC, HalftoneParams, halftone

W, H = 3000, 2000
PREVIEW_EDGE = 1000


def main() -> int:
    yy, xx = np.mgrid[0:H, 0:W]
    src = np.clip(0.5 + 0.45 * np.sin(xx / 120.0) * np.cos(yy / 95.0),
                  0, 1).astype(np.float32)
    Image.fromarray((src * 255).astype(np.uint8)).save(
        "docs/cmp_source.png")

    params = HalftoneParams(dot_shape=DOT_ORGANIC, stochastic=0.15)

    # ── 上排：应用的总览预览 ──────────────────────────────
    scale = PREVIEW_EDGE / W
    step = int(round(1 / scale))
    small = np.ascontiguousarray(src[::step, ::step])
    small = np.ascontiguousarray(small[:int(H * scale), :PREVIEW_EDGE])

    res_preview = max(params.resolution * scale,
                      3.0 * params.frequency)
    p_prev = HalftoneParams(
        resolution=res_preview, frequency=params.frequency,
        stochastic=params.stochastic, angle=params.angle,
        dot_shape=params.dot_shape, shape_amount=params.shape_amount,
        grain_scale=params.grain_scale, noise_size=params.noise_size,
        dot_gain=params.dot_gain, min_dot=params.min_dot,
        max_dot=params.max_dot, seed=params.seed)
    prev = halftone(small, p_prev)

    # ── 下排：实际产出缩到同一显示尺寸 ────────────────────
    full = halftone(src, params)
    ref = np.asarray(Image.fromarray(full, mode="L").resize(
        (small.shape[1], small.shape[0]), Image.LANCZOS))

    canvas = np.vstack([prev, ref])
    Image.fromarray(canvas, mode="L").save("docs/cmp_preview.png")

    print(f"源图 {W}x{H}   预览 {small.shape[1]}x{small.shape[0]} "
          f"(比例 {scale:.3f})")
    print(f"预览解析度 {res_preview:.0f} dpi  ->  cell "
          f"{max(1, round(res_preview / params.frequency))} px")
    print(f"实际解析度 {params.resolution:.0f} dpi  ->  cell "
          f"{max(1, round(params.resolution / params.frequency))} px")
    print("\n上排 = 预览   下排 = 实际产出（同样显示尺寸）")
    print("已存 docs/cmp_source.png 与 docs/cmp_preview.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
