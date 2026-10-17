"""絲網印刷半調墨點演算法核心。

設計要點（沿用 C 版經過驗證的邏輯）
  - 藍雜訊門檻場取代規則網格 → 顆粒位置自然隨機
  - 隨機網 / 有序網佔比連續可調 → 兩種質感之間無縫過渡
  - 墨點形狀可選（圓 / 方 / 橢圓）
  - 墨點不規則度：以角度諧波擾動墨點邊界，避免死板幾何形
  - 墨點擴大補償與最小/最大墨點夾限 → 對應網版印刷實務

輸出為二值（黑墨白底），適用於實際製版。

本模組只依賴 NumPy，與 UI 完全分離，可獨立測試。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .blue_noise import generate_blue_noise

__all__ = ["HalftoneParams", "halftone", "to_grayscale", "DOT_SHAPES",
           "physical_metrics", "DOT_ROUND", "DOT_SQUARE", "DOT_CROSS"]


# 墨點形狀
DOT_ROUND = 0
DOT_SQUARE = 1
DOT_CROSS = 2
DOT_ORGANIC = 3
DOT_SHAPES = ("圓形", "方形", "十字架", "有機隨機（銀鹽顆粒）")


@dataclass
class HalftoneParams:
    """半調墨點參數。

    stochastic 為「隨機墨點占比」：
        0.0 = 純隨機顆粒（藍雜訊分佈）
        1.0 = 傳統有序網格

    min_ink / max_ink 為「墨點大小範圍」，量綱是墨點覆蓋面積比例：
        0.0 = 紙白，完全沒有墨點
        1.0 = 完全密實填充

    注意：這兩個值直接以「墨量」表示。舊版的 min_dot / max_dot 夾在
    亮度 t 上（t=1 為白），方向與名稱相反，最淡墨點其實由 max_dot
    控制、高光碎點就是那樣來的。現在改以墨量為準，名實相符。
    """

    print_width_mm: float = 152.4     # 印刷寬度（mm，預設六寸）
    frequency: float = 40.0          # 網屏線數 lpi
    stochastic: float = 0.0          # 隨機墨點占比 0..1
    angle: float = 45.0              # 網屏角度（度）
    dot_shape: int = DOT_ROUND       # 墨點形狀
    shape_amount: float = 0.0        # 墨點不規則度 0..1
    noise_size: int = 64             # 藍雜訊尺寸
    dot_gain: float = 0.15           # 墨點擴大補償 0..0.6
    min_ink: float = 0.0             # 最小墨點覆蓋率 0..1
    max_ink: float = 1.0             # 最大墨點覆蓋率 0..1
    filter_mm: float = 0.0           # 最小墨點過濾（mm）；0 = 不過濾
    seed: int = 0                    # 隨機種子

    # 內部推導量：由介面依實際送去算的像素寬度算出，不開放編輯。
    # 舊版面板上有「解析度」滑桿，但它與「網屏線數」「顆粒粗細」
    # 三者只透過比值影響同一件事，而且面板顯示的值與實際送進演算的
    # 值並不相同（預覽時會暗中縮小）。現在改由「印刷寬度」推導。
    resolution: float = 750.0        # 推導：每吋像素數 dpi

    def validate(self) -> list[str]:
        """回傳錯誤訊息清單，空清單代表合法。"""
        errors = []
        if not (1.0 <= self.print_width_mm <= 10000.0):
            errors.append("印刷寬度須介於 1 ~ 10000 mm")
        if not (1.0 <= self.frequency <= 600.0):
            errors.append("網屏線數須介於 1 ~ 600 lpi")
        if not (0.0 <= self.stochastic <= 1.0):
            errors.append("隨機墨點占比須介於 0% ~ 100%")
        if not (0.0 <= self.angle <= 90.0):
            errors.append("網屏角度須介於 0 ~ 90 度")
        if not (0.0 <= self.shape_amount <= 1.0):
            errors.append("墨點不規則度須介於 0 ~ 1")
        if not (8 <= self.noise_size <= 128):
            errors.append("藍雜訊尺寸須介於 8 ~ 128")
        if not (0.0 <= self.dot_gain <= 0.6):
            errors.append("墨點擴大補償須介於 0 ~ 60%")
        if not (0.0 <= self.min_ink <= 1.0):
            errors.append("最小墨點覆蓋率須介於 0 ~ 100%")
        if not (0.0 <= self.max_ink <= 1.0):
            errors.append("最大墨點覆蓋率須介於 0 ~ 100%")
        if self.min_ink > self.max_ink:
            errors.append("最小墨點覆蓋率不可大於最大墨點覆蓋率")
        if not (0.0 <= self.filter_mm <= 100.0):
            errors.append("最小墨點過濾須介於 0 ~ 100 mm")
        if not (0 <= self.dot_shape < len(DOT_SHAPES)):
            errors.append("墨點形狀設定無效")
        if self.resolution <= 0.0:
            errors.append("解析度須為正值")
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
    """產生墨點中心的隨機位移場（藍雜訊決定）。

    這是隨機篩的核心：位移量取自藍雜訊，因此墨點雖然位置隨機，
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

    每顆墨點都會得到不同的一組係數，因此每顆顆粒的輪廓都是
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
    """以每顆墨點專屬的隨機諧波擾動輪廓，製造有機不規則顆粒。

    對每顆墨點取不同的高階諧波係數，沿角度方向拉伸或壓縮距離場，
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

    # 保證縮放係數為正，避免距離場翻轉造成墨點破碎
    return dist * np.maximum(1.0 + amp * mod, 0.15)


def _dot_metric(params: HalftoneParams, cell: int,
                y0: int, rows: int, width: int,
                origin_x: int = 0, origin_y: int = 0,
                full_w: int | None = None,
                full_h: int | None = None) -> np.ndarray:
    """到最近墨點中心的「形狀距離」場（整圖絕對座標）。

    位置與形狀是兩條獨立的軸：
      - 位置：由 stochastic 決定。100% 為規則網格，0% 為墨點
              中心各自隨機散開。
      - 形狀：由 dot_shape 決定，並對所有模式一致生效。

    距離越接近 0 代表越靠近墨點中心，在暗部會越早被填滿，
    墨點因此由中心向外自然長大 —— 這是 AM（振幅調變）網屏原理。

    重要：這裡一律使用「整張影像的絕對座標」，不對格點索引取模，
    也不做任何平鋪。早期實作把門檻場切成小磚重複貼滿全圖，導致
    24MP 影像上同一組隨機值重複兩萬多次，宏觀看又變回規則墨點，
    而且磚塊邊界會出現明顯接縫。

    origin_x / origin_y：目前陣列在「整張原圖」中的左上角座標。
    旋轉中心固定為整張原圖的中心，因此對同一區域單獨計算的結果
    與整圖計算完全一致 —— 這是細節放大窗格能與匯出檔逐像素相符的
    前提。若省略則視為從原圖 (0,0) 開始。

    full_w / full_h：整張原圖的尺寸，決定旋轉中心。
    """
    rad = math.radians(params.angle)
    ca, sa = math.cos(rad), math.sin(rad)

    fw = full_w if full_w else width
    fh = full_h if full_h else (origin_y + y0 + rows)

    # 以「整張原圖」的中心為旋轉中心，所有分帶共用同一套網格
    gx = np.arange(width, dtype=np.float64) + origin_x + 0.5
    gy = np.arange(y0, y0 + rows, dtype=np.float64) + origin_y + 0.5
    X = np.broadcast_to(gx, (rows, width))
    Y = np.broadcast_to(gy[:, None], (rows, width))

    cx = fw * 0.5
    cy = fh * 0.5
    rx = (X - cx) * ca - (Y - cy) * sa
    ry = (X - cx) * sa + (Y - cy) * ca

    # 所屬網格：使用絕對索引，橫跨整張影像都不會重複
    gi = np.rint(rx / cell).astype(np.int64)
    gj = np.rint(ry / cell).astype(np.int64)

    # 墨點中心 = 規則格點 + 隨機位移（有序模式位移為 0）
    amp = (1.0 - params.stochastic) * cell * 0.35
    if amp > 1e-6:
        jx = (_cell_rand(gi, gj, params.seed, 1) * 2.0 - 1.0) * amp
        jy = (_cell_rand(gi, gj, params.seed, 2) * 2.0 - 1.0) * amp
        dx = rx - (gi * cell + jx)
        dy = ry - (gj * cell + jy)
    else:
        dx = rx - gi * cell
        dy = ry - gj * cell

    # ── 形狀距離 ───────────────────────────────────────────
    if params.dot_shape == DOT_SQUARE:
        # 切比雪夫距離 -> 方形墨點
        dist = np.maximum(np.abs(dx), np.abs(dy))
    elif params.dot_shape == DOT_CROSS:
        # 十字架 = 水平臂 ∪ 垂直臂，兩者各自是矩形。
        #
        # 對單一矩形 max(|x|/a, |y|/b)，其等值線 {f <= t} 恰是該矩形；
        # 兩個矩形取最小值即為聯集，等值線因此正好是十字架，
        # 不是用圓角或疊加硬湊出來的近似形狀。
        arm = cell * 0.16       # 臂寬
        reach = cell * 0.48     # 臂長（未滿一格，滿墨時仍留白）
        ax = np.abs(dx)
        ay = np.abs(dy)
        bar_h = np.maximum(ax / reach, ay / arm)
        bar_v = np.maximum(ax / arm, ay / reach)
        dist = np.minimum(bar_h, bar_v)
    else:
        # 歐氏距離 -> 圓形墨點（有機隨機模式以此為基礎再擾動）
        dist = np.hypot(dx, dy)

    # 隨機有機模式：每顆顆粒套用專屬的隨機輪廓，模擬銀鹽晶體
    if params.dot_shape == DOT_ORGANIC:
        # 給一個足夠明顯的預設擾動量，讓顆粒輪廓清晰可辨
        amp_o = max(params.shape_amount, 0.55)
        dist = _organic_distort(dx, dy, dist, gi, gj, params.seed, amp_o)

    return dist


# 直方圖 CDF 的分箱數。距離場與色調無關，逐帶歸一化即可正確還原密度，
# 因此不需要完整排序；分箱數決定門檻的量化精度。
_CDF_BINS = 16384


def _rank_uniform(values: np.ndarray) -> np.ndarray:
    """把距離場轉為 0..1 上均勻分佈的門檻場（以直方圖近似 CDF）。

    為什麼需要這一步：墨點位置隨機抖動之後，相鄰墨點會互相靠近甚至
    重疊。此時單純用「面積正比於距離平方」計算，會把重疊的部分重複
    計入，導致暗部實際上墨率嚴重偏低（實測最多低估 30%）。

    把距離場歸一化成均勻分佈的門檻後，任意區塊的上墨率就會精確
    等於該區塊的暗度 —— 這正是有序抖動還原灰階的原理。

    用直方圖累積分布代替完整排序：距離場與色調無關，因此逐帶計算
    CDF 即可得到正確的局部密度，不必做全域排序。速度是排序的數倍，
    記憶體也只需 O(帶寬)。
    """
    flat = values.ravel()
    lo = float(flat.min())
    hi = float(flat.max())
    if hi <= lo:
        return np.zeros_like(values, dtype=np.float32)

    bins = _CDF_BINS
    pos = (flat - lo) * ((bins - 1) / (hi - lo))
    idx = np.clip(pos, 0, bins - 1).astype(np.int32)

    counts = np.bincount(idx, minlength=bins)
    cdf = np.cumsum(counts, dtype=np.float64)
    cdf /= cdf[-1]

    # 以相鄰 bin 做線性內插，精度優於 bin 寬度
    i0 = idx
    i1 = np.minimum(i0 + 1, bins - 1)
    frac = pos - i0
    out = cdf[i0] * (1.0 - frac) + cdf[i1] * frac

    return out.reshape(values.shape).astype(np.float32)



def _tie_break(gy: np.ndarray, gx: np.ndarray, seed: int) -> np.ndarray:
    """依網格座標產生固定的 0..1 亂數，用於決定該墨點的歸屬。

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
    """每個網屏格佔用的像素數。

    網屏線數（lpi）與解析度（dpi，每吋像素數）共同決定墨點大小：
    同一張圖印得越寬，格子在像素上就越大。

    這裡不再乘顆粒粗細倍率 —— 舊版「解析度 / 網屏線數 / 顆粒粗細」
    三個參數只透過比值影響同一件事，已合併為「印刷寬度 + 網屏線數」。
    """
    return max(1, min(512, int(round(params.resolution /
                                       params.frequency))))


def physical_metrics(params: HalftoneParams) -> dict[str, float]:
    """推算目前設定下的實體數值，供介面顯示。

    網屏線數決定墨點的物理間距；覆蓋率換成圓形墨點的直徑。
    這些值與影像像素數無關，只與「印多寬」和「幾 lpi」有關。
    """
    pitch_mm = 25.4 / params.frequency          # 墨點間距（mm）
    cell = _cell_px(params)                     # 間距（像素）
    dpi = params.resolution

    def diameter_mm(area: float) -> float:
        # 圓形墨點：面積比例 = π d² / (4 p²)  =>  d = 2p√(area/π)
        return 2.0 * pitch_mm * math.sqrt(max(0.0, area) / math.pi)

    def diameter_px(area: float) -> float:
        return diameter_mm(area) / 25.4 * dpi

    return {
        "dpi": dpi,
        "pitch_mm": pitch_mm,
        "pitch_px": float(cell),
        "mid_mm": diameter_mm(0.5),             # 50% 網調
        "mid_px": diameter_px(0.5),
        "min_mm": diameter_mm(params.min_ink),  # 範圍下限
        "min_px": diameter_px(params.min_ink),
        "max_mm": diameter_mm(params.max_ink),  # 範圍上限
        "max_px": diameter_px(params.max_ink),
        "filter_mm": params.filter_mm,
        # 過濾門檻換算成覆蓋率，供介面判斷是否過大
        "filter_area": (math.pi * (params.filter_mm / pitch_mm) ** 2 / 4.0
                        if params.filter_mm > 0.0 else 0.0),
    }


def halftone(gray: np.ndarray, params: HalftoneParams,
             origin: tuple[int, int] = (0, 0),
             full_shape: tuple[int, int] | None = None) -> np.ndarray:
    """將灰階圖轉為二值半調墨點（黑墨白底）。

    輸入 : (H, W) 或 (H, W, 1) 灰階，取值 0..1（0 = 黑）
    輸出 : (H, W) 的 uint8，0 = 滿墨（黑）、255 = 紙白

    origin：輸入陣列在「整張原圖」中的左上角座標 (x, y)。
    full_shape：整張原圖的尺寸 (寬, 高)，決定網格旋轉中心。
      傳入這兩項時，對同一區域單獨計算的結果會與整圖計算完全
      相同 —— 這是細節放大窗格能與匯出檔逐像素相符的前提。
      省略時視為整張影像即從 (0,0) 開始。
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

    # 墨點擴大補償：以 gamma 把中間調壓暗，使實際墨點面積增大
    t = _clamp01(tone)
    if params.dot_gain > 0.0:
        t = np.power(t, 1.0 + params.dot_gain)

    # 墨點大小範圍：以「墨量」夾限。
    # t 是亮度（1 = 白），暗度為 1 - t，因此要反轉：
    #   最小墨量 min_ink -> 亮度不得高於 1 - min_ink
    #   最大墨量 max_ink -> 亮度不得低於 1 - max_ink
    # 舊版寫成 clip(t, min_dot, max_dot)，等於用「最小墨點」去限制
    # 黑區、用「最大墨點」去限制白區，名實相反。預設 0.03 / 0.95
    # 會強迫純白區也有 4.9% 墨量，高光因此出現一堆只有幾像素的碎點。
    t = np.clip(t, 1.0 - params.max_ink, 1.0 - params.min_ink)

    # 最小墨點過濾：直徑小於門檻的墨點**整個捨棄、留白**。
    #
    # 這與 min_ink 方向相反：min_ink 是把墨點**撐大**到下限，
    # 過濾則是把過小的墨點**丟掉**，寧可留白也不印那種一兩個像素
    # 的碎點 —— 在絲印上，那種點不是印不出來就是糊成一團灰。
    #
    # 放在夾限之後，過濾才是最終裁決者：即使下限被調高，
    # 低於門檻的墨點依然不會印出來。
    if params.filter_mm > 0.0:
        pitch_mm = 25.4 / params.frequency
        # 圓形墨點：面積比例 a = π(d/p)²/4  =>  a = π(d/p)²/4
        a_min = math.pi * (params.filter_mm / pitch_mm) ** 2 / 4.0
        # 墨量 = 1 - t，低於門檻者直接設為純白
        t = np.where((1.0 - t) < a_min, 1.0, t)

    height, width = t.shape
    cell = _cell_px(params)

    ox, oy = origin
    if full_shape:
        full_w, full_h = full_shape
    else:
        full_w, full_h = ox + width, oy + height

    out = np.empty((height, width), dtype=np.uint8)

    # ── 分帶處理 ────────────────────────────────────────────
    # 一次算完整張影像會產生數個大型暫存陣列。分帶處理把記憶體
    # 壓在固定水位；因為距離場與色調無關，逐帶歸一化仍能讓
    # 每個區塊的上墨率精確還原其暗度。
    target_px = 1 << 21                      # 每帶約 200 萬像素
    strip = max(64, (target_px // max(1, width)))

    for y0 in range(0, height, strip):
        rows = min(strip, height - y0)
        dist = _dot_metric(params, cell, y0, rows, width,
                           origin_x=ox, origin_y=oy,
                           full_w=full_w, full_h=full_h)

        # 墨點不規則度：以低頻諧波擾動距離場，讓墨點邊界有機。
        # 隨機有機模式已在 _organic_distort 內逐顆擾動，此處略過。
        if params.shape_amount > 0.0 and params.dot_shape != DOT_ORGANIC:
            yy = (np.arange(rows, dtype=np.float64)[:, None] + oy + y0) / cell
            xx = (np.arange(width, dtype=np.float64)[None, :] + ox) / cell
            wobble = (np.sin(xx * 3.0 + yy * 2.0) * 0.6 +
                      np.sin(yy * 5.0 - xx * 1.0) * 0.4)
            dist = dist + wobble * (params.shape_amount * cell * 0.12)

        # 門檻場在 0..1 上均勻分佈，故上墨率恰等於該處暗度
        threshold = _rank_uniform(dist)

        dark = 1.0 - t[y0:y0 + rows]
        out[y0:y0 + rows] = np.where(dark > threshold, 0, 255)

    return out
