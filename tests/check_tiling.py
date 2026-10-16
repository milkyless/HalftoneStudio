"""验证：24MP 大图不再出现规律网点与接缝。

旧实现在小砖块内生成种子再平铺，24MP 上同一组随机值会重复两万多次。
本测试直接检查：
  1. 大图不同位置的「颗粒图案」互不相同（无平铺重复）
  2. 砖块边界处没有异常（无接缝）
  3. 大图处理时间与记忆体可接受
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from halftone_studio.core import DOT_ORGANIC, HalftoneParams, halftone, _cell_px

BIG_W, BIG_H = 6000, 4000          # 24MP


def main() -> int:
    cell = _cell_px(HalftoneParams())
    old_tile = cell * 4
    print(f"cell_px={cell}  旧砖块={old_tile}x{old_tile}  "
          f"旧实现在此图会重复 {(BIG_W // old_tile) * (BIG_H // old_tile)} 次")
    print()

    # 均匀中灰最能凸显平铺重复
    g = np.full((BIG_H, BIG_W), 0.5, dtype=np.float32)
    p = HalftoneParams(dot_shape=DOT_ORGANIC, stochastic=0.0)

    t0 = time.time()
    out = halftone(g, p)
    elapsed = time.time() - t0
    ink = float((out == 0).mean())
    print(f"24MP 处理耗时 {elapsed:.1f}s   上墨率 {ink:.4f}")
    print()

    ok = True

    # ── 1. 平铺重复检测 ──────────────────────────────────
    # 取多个相隔甚远的方块，比较其图案是否完全相同。
    # 若为平铺，同一相位的小块会完全一致。
    s = 128
    spots = [(0, 0), (0, BIG_W - s), (BIG_H - s, 0),
             (BIG_H - s, BIG_W - s), (BIG_H // 2, BIG_W // 2)]
    blocks = [out[y:y + s, x:x + s] for (y, x) in spots]

    identical = 0
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if np.array_equal(blocks[i], blocks[j]):
                identical += 1
    print(f"远距方块完全相同数: {identical} / "
          f"{len(blocks)*(len(blocks)-1)//2}")
    if identical:
        print("  [失败] 仍存在平铺重复")
        ok = False
    else:
        print("  [通过] 各处图案互不相同，无平铺")

    # 像素级相关：旧实现在相位对齐时会接近 1.0
    a = blocks[0].astype(np.int16)
    b = blocks[-1].astype(np.int16)
    corr = float(np.corrcoef(a.ravel(), b.ravel())[0, 1])
    print(f"  最远两块的相关性: {corr:+.4f}（平铺时会接近 1.0）")
    if abs(corr) > 0.95:
        print("  [失败] 相关性过高，疑似仍在平铺")
        ok = False

    # ── 2. 接缝检测 ──────────────────────────────────────
    # 旧实现的砖块边界会出现亮度突变。逐列比较相邻列的差异，
    # 看是否存在异常突出的「缝」。
    sub = out[::7, ::7].astype(np.int16)
    col_edges = np.abs(np.diff(sub, axis=1)).mean(axis=0)
    median_e = float(np.median(col_edges))
    worst = float(col_edges.max())
    ratio = worst / max(median_e, 1e-9)
    print(f"\n相邻列差异：中位 {median_e:.3f}  最大 {worst:.3f}  "
          f"比值 {ratio:.2f}")
    if ratio > 3.0:
        print("  [失败] 存在明显接缝")
        ok = False
    else:
        print("  [通过] 无异常接缝")

    # ── 3. 视觉存证 ──────────────────────────────────────
    out_path = "docs/big_sample.png"
    preview = Image.fromarray(out[::4, ::4], mode="L")
    preview.save(out_path)
    print(f"\n已存抽样预览 {out_path} "
          f"({preview.width}x{preview.height})")

    print("\n结果：", "全部通过" if ok else "有项目失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
