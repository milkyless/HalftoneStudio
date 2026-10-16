"""藍雜訊門檻場生成（void-and-cluster）。

沿用 C 版經過驗證的演算法：
  階段一  由稀疏的隨機圖樣逐步「挖空」，得到由緊密到疏鬆的排序
  階段二  再逐步「填入」，補足剩下的像素

關鍵改進（原 C 版首輪的缺陷）：
  挑選最優像素時加入隨機微擾來打破並列。
  若永遠取第一個最大值，反覆執行會沿固定方向累積成條帶狀偽影。

本模組純粹使用 NumPy，不依賴任何圖形函式庫，可獨立測試。
"""
from __future__ import annotations

import numpy as np

__all__ = ["generate_blue_noise"]

# 距離場每重新計算一次可處理多少個像素
_RELAX_BATCH = 48


def _wrap_min(d: np.ndarray) -> np.ndarray:
    """四方向環狀鄰域最小值 +1，用於距離場鬆弛。"""
    return np.minimum.reduce([
        d,
        np.roll(d, 1, axis=0) + 1.0,
        np.roll(d, -1, axis=0) + 1.0,
        np.roll(d, 1, axis=1) + 1.0,
        np.roll(d, -1, axis=1) + 1.0,
    ])


def _distance_field(seeds: np.ndarray) -> np.ndarray:
    """以環狀邊界做迭代鬆弛，求每個像素到最近種子距離。"""
    d = np.where(seeds, 0.0, 1e9)
    for _ in range(int(seeds.shape[0]) * 2):
        prev = d
        d = _wrap_min(d)
        if np.array_equal(d, prev):
            break
    return d


def _tie_break_field(size: int, seed: int) -> np.ndarray:
    """產生固定的隨機微擾欄位，用於打破並列。

    使用固定種子，因此同一 (size, seed) 一定得到相同結果，
    讓參數微調可以重現。
    """
    rng = np.random.default_rng(seed * 2654435761 % (2 ** 32))
    return rng.random((size, size))


def generate_blue_noise(size: int = 64, seed: int = 0) -> np.ndarray:
    """產生 size×size 的藍雜訊門檻場，取值 0..1 且分佈均勻。

    回傳的陣列可直接作為門檻場使用：灰階高於門檻即上墨。
    """
    if size < 8:
        size = 8

    n = size * size
    rng = np.random.default_rng(seed)
    tie = _tie_break_field(size, seed)

    # 初始圖樣：約 10% 隨機撒點
    binary = rng.random((size, size)) < 0.10
    if not binary.any():
        binary[size // 2, size // 2] = True

    n_dots = int(binary.sum())
    target = max(1, n_dots // 2)

    ranking = np.empty(n, dtype=np.int32)
    used = np.zeros(n, dtype=bool)
    k = 0

    # ── 階段一：挖空（移除最孤立的網點）────────────────────────
    dist = _distance_field(~binary)
    since = 0

    while n_dots > target and k < n:
        score = dist * 4.0 + tie
        score = np.where(binary, score, -1.0)
        best = int(np.argmax(score))

        row, col = divmod(best, size)
        binary[row, col] = False
        n_dots -= 1
        ranking[k] = best
        used[best] = True
        k += 1

        since += 1
        if since >= _RELAX_BATCH:
            dist = _distance_field(~binary)
            since = 0

    # ── 階段二：填入（補上最不擁擠的位置）────────────────────
    dist = _distance_field(binary)
    since = 0

    while n_dots < n and k < n:
        score = dist * 4.0 + tie
        score = np.where(binary, -1.0, score)
        best = int(np.argmax(score))

        # 防禦：若 argmax 因陳舊距離場而選到已占用的像素，
        # 退回選擇尚未填入門檻的最小索引，確保每個像素恰好排名一次。
        if binary[divmod(best, size)]:
            remaining = np.flatnonzero(~used[best])
            best = int(remaining[0]) if remaining.size else -1
            if best < 0:
                break

        row, col = divmod(best, size)
        binary[row, col] = True
        n_dots += 1
        ranking[k] = best
        used[best] = True
        k += 1

        since += 1
        if since >= _RELAX_BATCH:
            dist = _distance_field(binary)
            since = 0

    # ── 以排名填入門檻，使分佈在 0..1 上均勻 ────────────────
    # 使用 zeros 而非 empty，保證任何未排名像素都有安全預設值。
    field = np.full(n, 0.5, dtype=np.float32)
    field[ranking[:k]] = np.arange(k, dtype=np.float32) / max(1, k - 1)

    return field.reshape(size, size)
