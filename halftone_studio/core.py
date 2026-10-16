"""絲網印刷半調網點演算法核心。

設計要點（沿用 C 版經過驗證的邏輯）
  - 藍雜訊門檻場取代規則網格 → 顆粒位置自然隨機
  - 隨機網 / 有序網佔比連續可調 → 兩種質感之間無縫過渡
  - 網點形狀可選（圓 / 方 / 橢圓）
  - 網點不規則度：以角度諧波擾動網點邊界，避免死板幾何形
  - 網點擴大補償與最小/最大網點夾限 → 對應網版印刷實務

輸出為二值（黑墨白底），適用於實際製版。

本模組只依賴 NumPy，與 UI 完全分離，可獨立測試。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .blue_noise import generate_blue_noise

__all__ = ["HalftoneParams", "halftone", "to_grayscale", "DOT_SHAPES",
           "DOT_ROUND", "DOT_SQUARE", "DOT_ELLIPSE"]


# 網點形狀
DOT_ROUND = 0
DOT_SQUARE = 1
DOT_ELLIPSE = 2
DOT_ORGANIC = 3
DOT_SHAPES = ("圓形", "方形", "橢圓形", "隨機有機（銀鹽顆粒）")


@dataclass
class HalftoneParams:
    """半調網點參數。

    stochastic 為「隨機網占比」：
        0.0 = 純隨機顆粒（藍雜訊分佈）
        1.0 = 傳統有序網格
    """

    resolution: float = 300.0      # 輸入解析度 dpi
    frequency: float = 40.0        # 網點頻率 lpi
    stochastic: float = 0.0        # 隨機網占比 0..1
    angle: float = 45.0            # 網屏角度（度）
    dot_shape: int = DOT_ROUND     # 網點形狀
    shape_amount: float = 0.0      # 網點不規則度 0..1
    grain_scale: float = 1.0       # 顆粒粗細倍率 0.1..8
    noise_size: int = 64           # 藍雜訊尺寸
    dot_gain: float = 0.15         # 網點擴大補償 0..0.6
    min_dot: float = 0.03          # 最小網點 0..1
    max_dot: float = 0.95          # 最大網點 0..1
    seed: int = 0                  # 隨機種子

    def validate(self) -> list[str]:
        """回傳錯誤訊息清單，空清單代表合法。"""
        errors = []
        if not (1.0 <= self.resolution <= 4800.0):
            errors.append("解析度須介於 1 ~ 4800 dpi")
        if not (1.0 <= self.frequency <= 600.0):
            errors.append("網點頻率須介於 1 ~ 600 lpi")
        if not (0.0 <= self.stochastic <= 1.0):
            errors.append("隨機網占比須介於 0% ~ 100%")
        if not (0.0 <= self.angle <= 90.0):
            errors.append("網屏角度須介於 0 ~ 90 度")
        if not (0.0 <= self.shape_amount <= 1.0):
            errors.append("網點不規則度須介於 0 ~ 1")
        if not (0.1 <= self.grain_scale <= 8.0):
            errors.append("顆粒粗細須介於 0.1 ~ 8.0")
        if not (8 <= self.noise_size <= 128):
            errors.append("藍雜訊尺寸須介於 8 ~ 128")
        if not (0.0 <= self.dot_gain <= 0.6):
            errors.append("網點擴大補償須介於 0 ~ 60%")
        if not (0.0 <= self.min_dot <= 1.0):
            errors.append("最小網點須介於 0 ~ 1")
        if not (0.0 <= self.max_dot <= 1.0):
            errors.append("最大網點須介於 0 ~ 1")
        if self.min_dot > self.max_dot:
            errors.append("最小網點不可大於最大網點")
        if not (0 <= self.dot_shape < len(DOT_SHAPES)):
            errors.append("網點形狀設定無效")
        if self.seed < 0:
            errors.append("隨機種子不可為負數")
        return errors


def _clamp01(a: np.ndarray) -> np.ndarray:
    return np.clip(a, 0.0, 1.0)


def to_grayscale(rgb: np.ndarray) -> np.ndarray:
    """Rec.709 亮度換算，輸入 (H, W, 3) 或 (H, W, 4)，回傳 (H, W) 灰階。

    回傳值 0..1，0 = 黑、1 = 白。
    """
    a = np.asarray(rgb, dtype=np.float32)
    if a.ndim != 3:
        raise ValueError("灰階轉換需要 (H, W, 3) 或 (H, W, 4) 的陣列")

    c = a[:, :, :3]
    lum = (0.2126 * c[:, :, 0] +
           0.7152 * c[:, :, 1] +
           0.0722 * c[:, :, 2])
    return _clamp01(lum)


def _jitter_field(n_cells: int, noise_size: int, seed: int,
                  amp: float) -> tuple[np.ndarray, np.ndarray]:
    """產生網點中心的隨機位移場（藍雜訊決定）。

    這是隨機篩的核心：位移量取自藍雜訊，因此網點雖然位置隨機，
    彼此間距卻保持均勻，不會出現成團或空隙。

    n_cells 為單一方向的網格數；回傳的場以 n_cells 為週期，
    確保平鋪時無縫。
    """
    size = max(8, min(128, noise_size))
    bx = generate_blue_noise(size, seed)
    by = generate_blue_noise(size, seed + 7919)

    # 均勻取樣整個藍雜訊場，而非只取角落數個值
    idx = (np.arange(n_cells) * size // n_cells).clip(0, size - 1)
    ox = (bx[np.ix_(idx, idx)].astype(np.float64) * 2.0 - 1.0) * amp
    oy = (by[np.ix_(idx, idx)].astype(np.float64) * 2.0 - 1.0) * amp
    return ox, oy


def _cell_rand(gi: np.ndarray, gj: np.ndarray, seed: int,
               channel: int) -> np.ndarray:
    """依網格座標產生固定的 0..1 亂數。

    每顆網點都會得到不同的一組係數，因此每顆顆粒的輪廓都是
    獨一無二的 —— 這正是膠片銀鹽顆粒的特徵，而不是重複的幾何圖形。

    全程使用 uint64 陣列運算：numpy 的陣列乘法會靜默回繞（符合
    我們要的雜湊語意），但標量乘法會丟出 overflow 警告，因此
    種子項也必須建成陣列。
    """
    salt = np.uint64((int(seed) + int(channel) * 7919) & 0xFFFFFFFFFFFFFFFF)

    h = gi.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)
    h = h + gj.astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
    h = h + salt
    h ^= h >> np.uint64(29)
    h = h * np.uint64(0xBF58476D1CE4E5B9)
    h ^= h >> np.uint64(32)
    return (h >> np.uint64(40)).astype(np.float64) / float(1 << 24)


def _organic_distort(dx: np.ndarray, dy: np.ndarray, dist: np.ndarray,
                     gi: np.ndarray, gj: np.ndarray, seed: int,
                     amp: float) -> np.ndarray:
    """以每顆網點專屬的隨機諧波擾動輪廓，製造有機不規則顆粒。

    對每顆網點取不同的高階諧波係數，沿角度方向拉伸或壓縮距離場，
    使輪廓成為有機的多瓣形，而非單調的圓或方。

    因為擾動是「每顆各自不同」，不會出現整張圖重複同一圖樣的呆板感。
    """
    r = np.hypot(dx, dy) + 1e-9
    theta = np.arctan2(dy, dx)

    mod = np.zeros_like(dist)
    # 高階諧波讓輪廓更不規則，同時保持封閉平滑
    for k, weight in ((2, 0.50), (3, 0.32), (5, 0.18)):
        a = _cell_rand(gi, gj, seed, k) * 2.0 - 1.0
        p = _cell_rand(gi, gj, seed, k + 10) * math.tau
        mod += weight * a * np.sin(k * theta + p)

    # 保證縮放係數為正，避免距離場翻轉造成網點破碎
    return dist * np.maximum(1.0 + amp * mod, 0.15)


def _dot_metric(params: HalftoneParams, cell: int,
                tile: int) -> np.ndarray:
    """到最近網點中心的「形狀距離」場。

    位置與形狀是兩條獨立的軸：
      - 位置：由 stochastic 決定。100% 為規則網格，
              0% 為藍雜訊隨機散開的網點。
      - 形狀：由 dot_shape 決定，並對所有模式一致生效。
              因為無論網點落在哪裡，都用同一套形狀距離度量。

    距離越接近 0 代表越靠近網點中心，在暗部會越早被填滿，
    網點因此由中心向外自然長大 —— 這是 AM（振幅調變）網屏原理。
    """
    rad = math.radians(params.angle)
    ca, sa = math.cos(rad), math.sin(rad)

    half = tile * 0.5
    gx, gy = np.meshgrid(np.arange(tile, dtype=np.float64),
                         np.arange(tile, dtype=np.float64))
    rx = (gx + 0.5 - half) * ca - (gy + 0.5 - half) * sa
    ry = (gx + 0.5 - half) * sa + (gy + 0.5 - half) * ca

    # 所屬網格（tile 為 cell 的整數倍，故可整除）
    n = max(1, tile // cell)
    gi = np.round(rx / cell).astype(np.int64)
    gj = np.round(ry / cell).astype(np.int64)
    gi_m = np.mod(gi, n)
    gj_m = np.mod(gj, n)

    # 網點中心 = 規則格點 + 藍雜訊位移（有序模式位移為 0）
    amp = (1.0 - params.stochastic) * cell * 0.35
    if amp > 1e-6:
        ox, oy = _jitter_field(n, params.noise_size, params.seed, amp)
        dx = rx - (gi * cell + ox[gi_m, gj_m])
        dy = ry - (gj * cell + oy[gi_m, gj_m])
    else:
        dx = rx - gi * cell
        dy = ry - gj * cell

    # ── 形狀距離 ───────────────────────────────────────────
    if params.dot_shape == DOT_SQUARE:
        # 切比雪夫距離 -> 方形網點
        dist = np.maximum(np.abs(dx), np.abs(dy))
    elif params.dot_shape == DOT_ELLIPSE:
        # 沿旋轉軸拉伸 -> 橢圓網點
        dist = np.hypot(dx / 1.5, dy / 0.78)
    else:
        # 歐氏距離 -> 圓形網點（隨機有機模式以此為基礎再擾動）
        dist = np.hypot(dx, dy)

    # 隨機有機模式：每顆顆粒套用專屬的隨機輪廓，模擬銀鹽晶體
    if params.dot_shape == DOT_ORGANIC:
        # 給一個足夠明顯的預設擾動量，讓顆粒輪廓清晰可辨
        amp = max(params.shape_amount, 0.55)
        dist = _organic_distort(dx, dy, dist, gi, gj, params.seed, amp)

    return dist



def _rank_uniform(values: np.ndarray) -> np.ndarray:
    """把任意數值場轉為 0..1 上均勻分佈的門檻場。

    排名化是關鍵：門檻均勻分佈時，每個區塊的上墨率才會精確
    等於該區塊的暗度，這是有序抖動能正確還原灰階的前提。
    """
    flat = values.ravel()
    order = np.argsort(flat, kind="stable")
    out = np.empty(flat.size, dtype=np.float32)
    out[order] = np.linspace(0.0, 1.0, flat.size, dtype=np.float32)
    return out.reshape(values.shape)


def _tie_break(gy: np.ndarray, gx: np.ndarray, seed: int) -> np.ndarray:
    """依網格座標產生固定的 0..1 亂數，用於決定該網點的歸屬。

    使用確定性雜湊，確保同一 seed 必定得到相同結果，
    讓參數微調可以重現。
    """
    h = (gy.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15) +
         gx.astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F) +
         np.uint64(seed) * np.uint64(0x165667B19E3779F9))
    h ^= h >> np.uint64(29)
    h = h * np.uint64(0xBF58476D1CE4E5B9)
    h ^= h >> np.uint64(32)
    return (h >> np.uint64(40)).astype(np.float64) / float(1 << 24)


def _cell_px(params: HalftoneParams) -> int:
    """每個網點網格佔用的像素數。

    lpi（每吋線數）與 dpi（每吋點數）共同決定網點實際大小。
    grain_scale 用來整體放大或縮小顆粒。
    """
    raw = params.resolution / params.frequency * params.grain_scale
    return max(1, min(512, int(round(raw))))


def _build_threshold(params: HalftoneParams,
                     out_shape: tuple[int, int]) -> np.ndarray:
    """產生套用到整張影像的門檻場（0..1，均勻分佈）。

    隨機網與有序網依 stochastic 連續過渡：
        1.0 = 傳統重複網點網格
        0.0 = 藍雜訊隨機顆粒
    """
    cell = _cell_px(params)
    # 磚大小取網格的整數倍，確保網格能無縫對接
    tile = cell * 4

    # 形狀距離場：同時帶入網點位置（有序 / 隨機）與網點形狀
    base = _dot_metric(params, cell, tile)

    # 網點不規則度：以低頻諧波擾動距離場，讓網點邊界有機而不死板。
    # 隨機有機模式已在 _organic_distort 內做逐顆擾動，此處略過避免疊加。
    # 在排名化之前施加，因此不影響整體密度還原。
    if params.shape_amount > 0.0 and params.dot_shape != DOT_ORGANIC:
        yy, xx = np.mgrid[0:tile, 0:tile].astype(np.float64)
        yy = yy / tile * math.tau
        xx = xx / tile * math.tau
        wobble = (np.sin(xx * 3.0 + yy * 2.0) * 0.6 +
                  np.sin(yy * 5.0 - xx * 1.0) * 0.4)
        base = base + wobble * (params.shape_amount * cell * 0.12)

    th = _rank_uniform(base)

    # 以索引取模平鋪，避免複製整塊磚造成記憶體暴增
    rows = np.arange(out_shape[0], dtype=np.int32) % tile
    cols = np.arange(out_shape[1], dtype=np.int32) % tile
    return th[np.ix_(rows, cols)]



def halftone(gray: np.ndarray, params: HalftoneParams) -> np.ndarray:
    """將灰階圖轉為二值半調網點（黑墨白底）。

    輸入 : (H, W) 或 (H, W, 1) 灰階，取值 0..1（0 = 黑）
    輸出 : (H, W) 的 uint8，0 = 滿墨（黑）、255 = 紙白
    """
    errors = params.validate()
    if errors:
        raise ValueError("；".join(errors))

    tone = np.asarray(gray, dtype=np.float32)
    if tone.ndim == 3:
        tone = tone[:, :, 0]
    if tone.ndim != 2:
        raise ValueError("半調處理需要 (H, W) 的灰階陣列")
    if tone.size == 0:
        raise ValueError("影像為空，無法處理")

    # 網點擴大補償：以 gamma 把中間調壓暗，使實際網點面積增大
    t = _clamp01(tone)
    if params.dot_gain > 0.0:
        t = np.power(t, 1.0 + params.dot_gain)

    # 最小 / 最大網點夾限：暗部保留細節、高光避免死黑
    t = np.clip(t, params.min_dot, params.max_dot)

    threshold = _build_threshold(params, tone.shape)

    # ── 二值判定 ────────────────────────────────────────────
    # 灰階越暗代表該處該上越多的墨。
    # 門檻場在 0..1 上均勻分佈，故任何區塊的上墨率恰等於
    # 該區塊的暗度 1 - tone —— 這正是有序抖動的原理，
    # 無需任何全域密度校準。
    ink = t < (1.0 - threshold)
    return np.where(ink, 0, 255).astype(np.uint8)
