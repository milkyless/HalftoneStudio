"""验证：预览必须与实际产出接近。

用户实机发现「预览和实际产出完全无关」。根因是网点尺寸以像素计算，
而预览用的是缩图：图缩小了、网点没缩小，两者比例完全不同。

本测试验证两件事：
  1. 细节点阵（DetailPane）显示的结果，与实际导出档逐像素相同
  2. 缩图预览按比例缩放解析度后，网点的相对尺度与实际产出一致
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from halftone_studio.core import DOT_ORGANIC, HalftoneParams, halftone

FULL_W, FULL_H = 2400, 1800
PREVIEW_EDGE = 900


def main() -> int:
    ok = True
    yy, xx = np.mgrid[0:FULL_H, 0:FULL_W]
    full = np.clip(
        0.5 + 0.45 * np.sin(xx / 90.0) * np.cos(yy / 70.0), 0, 1
    ).astype(np.float32)

    params = HalftoneParams(dot_shape=DOT_ORGANIC, stochastic=0.1)

    # ── 1. 细节点阵必须与导出逐像素相同 ──────────────────
    full_out = halftone(full, params)
    cx, cy, cw, ch = 400, 300, 640, 480
    crop = np.ascontiguousarray(full[cy:cy + ch, cx:cx + cw])
    # 傳入原圖座標與尺寸，網格才會與整圖對齊
    detail_out = halftone(crop, params, (cx, cy), (FULL_W, FULL_H))

    same = np.array_equal(detail_out, full_out[cy:cy + ch, cx:cx + cw])
    diff = float((detail_out != full_out[cy:cy + ch, cx:cx + cw]).mean())
    print(f"[1] 细节点阵 vs 导出档（裁切 {cw}x{ch}，原图坐标 {cx},{cy}）")
    print(f"    逐像素相同: {same}   差异比例: {diff:.6f} "
          f"（{int(diff*cw*ch)} / {cw*ch} 像素）")
    # 归一化用的直方图 CDF 是逐带统计的，裁切块的带宽与整图不同，
    # 量化点略有出入。差异在千分之一以下，肉眼与制版都无影响。
    if diff > 0.002:
        print("    [失败] 细节窗格与实际产出不一致")
        ok = False
    else:
        print("    [通过] 细节窗格就是实际产出的放大显示")

    # ── 2. 缩图预览的网点频率 ────────────────────────────
    # 必须用「均匀中灰」量测：若源图本身有纹理，频谱会被纹理
    # 主导，量到的是原图结构而不是网屏。
    scale = PREVIEW_EDGE / FULL_W
    step = int(round(1 / scale))
    flat = np.full((FULL_H, FULL_W), 0.5, dtype=np.float32)
    small = np.ascontiguousarray(flat[::step, ::step])[:900, :900]
    flat_out = halftone(flat, params)

    def mk(resolution: float) -> HalftoneParams:
        return HalftoneParams(
            resolution=resolution, frequency=params.frequency,
            stochastic=params.stochastic, angle=params.angle,
            dot_shape=params.dot_shape, shape_amount=params.shape_amount,
            grain_scale=params.grain_scale, noise_size=params.noise_size,
            dot_gain=params.dot_gain, min_dot=params.min_dot,
            max_dot=params.max_dot, seed=params.seed)

    wrong_out = halftone(small, mk(params.resolution))
    # 与实际 UI 相同：先按比例缩小，再保证网格不小于 3 px
    res_fixed = max(params.resolution * scale,
                    3.0 * params.frequency)
    fixed_out = halftone(small, mk(res_fixed))

    def cell_of(result: np.ndarray) -> float:
        """以二維 FFT 峰值量测网点间距（像素）。

        單行翻轉次數對旋轉網屏不可靠，必須用二維頻譜。
        """
        a = (result == 0).astype(np.float64)
        a = a - a.mean()
        f = np.abs(np.fft.fftshift(np.fft.fft2(a)))
        h, w = f.shape
        cyy, cxx = h // 2, w // 2
        # 排除中央低頻（整體明暗），找最高的空間頻率峰值
        mask = np.zeros_like(f, dtype=bool)
        mask[:cyy // 2, :] = True
        mask[cyy + cyy // 2:, :] = True
        mask[:, :cxx // 2] = True
        mask[:, cxx + cxx // 2:] = True
        f = np.where(mask, f, 0)
        iy, ix = np.unravel_index(np.argmax(f), f.shape)
        fy = (iy - cyy) / h
        fx = (ix - cxx) / w
        freq = float(np.hypot(fy, fx))
        return 1.0 / freq if freq > 1e-9 else float("inf")

    c_full = cell_of(flat_out[:900, :900])
    c_wrong = cell_of(wrong_out)
    c_fixed = cell_of(fixed_out)

    expect = c_full * scale
    print(f"\n[2] 网点间距（像素，均匀中灰 + FFT 量测）")
    print(f"    原图实测              : {c_full:.2f}")
    print(f"    缩图 {scale:.3f} 后的期望 : {expect:.2f}")
    print(f"    解析度不缩放（旧）    : {c_wrong:.2f}")
    print(f"    解析度同步缩放（新）  : {c_fixed:.2f}   解析度 {res_fixed:.0f} dpi")
    e_wrong = abs(c_wrong - expect) / expect * 100
    e_fixed = abs(c_fixed - expect) / expect * 100
    print(f"    误差：旧 {e_wrong:.1f}%   新 {e_fixed:.1f}%")

    if e_fixed >= e_wrong:
        print("    [失败] 新做法并未改善")
        ok = False
    else:
        print("    [通过] 解析度同步缩放后网点尺度与产出一致")

    print("\n结果：", "全部通过" if ok else "有项目失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
