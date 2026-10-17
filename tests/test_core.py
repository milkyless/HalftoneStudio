"""演算法測試。

執行方式：
    .venv\\Scripts\\python.exe -m pytest tests -v
或直接：
    .venv\\Scripts\\python.exe tests\\test_core.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from halftone_studio.blue_noise import generate_blue_noise  # noqa: E402
from halftone_studio.core import (  # noqa: E402
    DOT_CROSS, DOT_ORGANIC, DOT_ROUND, DOT_SQUARE, HalftoneParams, halftone,
    physical_metrics, to_grayscale,
)


def _flat(**kw) -> HalftoneParams:
    """不含夾限與擴大的參數，便於檢驗密度還原。"""
    base = dict(min_ink=0.0, max_ink=1.0, dot_gain=0.0)
    base.update(kw)
    return HalftoneParams(**base)


def _gradients(w: int = 400, h: int = 200) -> np.ndarray:
    """水平漸層測試圖。"""
    return np.tile(np.linspace(0, 1, w, dtype=np.float32), (h, 1))


def _difference(a: np.ndarray, b: np.ndarray) -> float:
    """兩張圖的平均差異百分比（0..100）。"""
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()
                 / 255.0 * 100.0)


def _max_density_error(params: HalftoneParams, blocks: int = 8) -> float:
    img = _gradients()
    out = halftone(img, params)
    step = img.shape[1] // blocks
    err = 0.0
    for i in range(blocks):
        s = slice(i * step, (i + 1) * step)
        ink = float((out[:, s] == 0).mean())
        err = max(err, abs(ink - (1.0 - float(img[:, s].mean()))))
    return err


# ── 藍雜訊 ──────────────────────────────────────
def test_blue_noise_range():
    """門檻場必須落在 0..1，且數值幾乎互異。"""
    f = generate_blue_noise(48, seed=0)
    assert f.shape == (48, 48)
    assert 0.0 <= f.min() and f.max() <= 1.0
    # 若有大量重複，代表排名有誤（早期實作曾出現此缺陷）
    assert len(np.unique(f)) > f.size * 0.9


def test_blue_noise_uniform_density():
    """藍雜訊必須讓各區塊密度接近 0.5。"""
    f = generate_blue_noise(64, seed=0)
    blocks = f.reshape(8, 8, 8, 8).mean(axis=(1, 3))
    assert blocks.std() < 0.12, f"密度標準差過大：{blocks.std():.3f}"


def test_blue_noise_deterministic():
    """同一種子必須產生完全相同的結果。"""
    a = generate_blue_noise(32, seed=7)
    b = generate_blue_noise(32, seed=7)
    assert np.array_equal(a, b)


# ── 灰階與輸出 ──────────────────────────────────
def test_to_grayscale():
    """Rec.709 亮度換算。"""
    rgb = np.zeros((1, 3, 3), dtype=np.float32)
    rgb[0, 0] = (1.0, 0.0, 0.0)
    rgb[0, 1] = (0.0, 1.0, 0.0)
    rgb[0, 2] = (0.0, 0.0, 1.0)
    g = to_grayscale(rgb)[0]
    assert abs(g[0] - 0.2126) < 1e-4
    assert abs(g[1] - 0.7152) < 1e-4
    assert abs(g[2] - 0.0722) < 1e-4


def test_output_is_binary():
    """輸出必須是純二值，黑墨白底。"""
    out = halftone(_gradients(200, 100), _flat())
    assert out.dtype == np.uint8
    assert set(np.unique(out)) <= {0, 255}


def test_tone_relationship():
    """越暗的區塊上墨率必須越高。"""
    img = _gradients(400, 100)
    out = halftone(img, _flat())
    inks = [float((out[:, i * 100:(i + 1) * 100] == 0).mean())
            for i in range(4)]
    assert inks == sorted(inks, reverse=True), f"上墨率非遞減：{inks}"


# ── 密度還原 ────────────────────────────────────
# 容差 3%。隨機篩的網點位置本來就有抖動，局部密度天生會有起伏
# （實測有序網約 0.7%、純隨機網約 2.1%），此容差只為抓出真正的
# 迴歸錯誤 —— 早期有缺陷的實作誤差曾達 90%。
DENSITY_TOLERANCE = 0.03


def test_density_reproduction():
    """任意模式的上墨率都必須還原原始暗度。"""
    for st in (0.0, 0.35, 0.7, 1.0):
        err = _max_density_error(_flat(stochastic=st))
        assert err < DENSITY_TOLERANCE, \
            f"stochastic={st} 密度誤差 {err:.4f} 過大"


def test_density_reproduction_all_shapes():
    """四種網點形狀都必須正確還原密度。"""
    for shape in (DOT_ROUND, DOT_SQUARE, 2, DOT_ORGANIC):
        err = _max_density_error(_flat(dot_shape=shape, stochastic=0.5))
        assert err < DENSITY_TOLERANCE, \
            f"形狀 {shape} 密度誤差 {err:.4f} 過大"


# ── 參數確實生效 ────────────────────────────────
def test_shape_affects_all_modes():
    """形狀參數在隨機與有序模式下都必須有效。

    重要的回歸測試：早期實作把形狀綁在有序網上，
    純隨機模式下形狀完全無效（差異 0.00%）。
    """
    img = np.full((200, 200), 0.5, dtype=np.float32)
    for st in (0.0, 0.5, 1.0):
        ref = halftone(img, _flat(stochastic=st, dot_shape=DOT_ROUND))
        sq = halftone(img, _flat(stochastic=st, dot_shape=DOT_SQUARE))
        assert _difference(ref, sq) > 2.0, f"stochastic={st} 形狀無效"


def test_organic_shape_is_distinct():
    """隨機有機形狀必須明顯不同於圓形。"""
    img = np.full((200, 200), 0.5, dtype=np.float32)
    rnd = halftone(img, _flat(dot_shape=DOT_ROUND))
    org = halftone(img, _flat(dot_shape=DOT_ORGANIC))
    assert _difference(rnd, org) > 5.0


def test_frequency_affects_dot_size():
    """網屏線數必須實際改變輸出（舊版的「顆粒粗細」已併入此項）。"""
    img = np.full((200, 200), 0.5, dtype=np.float32)
    ref = halftone(img, _flat())
    fine = halftone(img, _flat(frequency=80.0))
    assert _difference(ref, fine) > 10.0


def test_cross_shape_is_distinct():
    """十字架形狀必須明顯不同於圓形與方形。"""
    img = np.full((200, 200), 0.5, dtype=np.float32)
    rnd = halftone(img, _flat(dot_shape=DOT_ROUND))
    cross = halftone(img, _flat(dot_shape=DOT_CROSS))
    assert _difference(rnd, cross) > 5.0


def test_cross_corners_stay_white():
    """十字架的四角必須留白；方形則填滿整格。

    直接檢驗距離場：對同一門檻，方形的墨區會填滿其外接矩形
    （密度 1.0），十字架則因四角留白而低於 1.0。這是兩者最根本的
    差異，比比較上墨率可靠（上墨率本來就被歸一化成一樣）。
    """
    from halftone_studio.core import _dot_metric

    cell = 40
    p = HalftoneParams(dot_shape=DOT_CROSS, stochastic=1.0, angle=0.0,
                       frequency=1000.0 / cell, resolution=1000.0)
    d_cross = _dot_metric(p, cell, 0, cell, cell)
    p2 = HalftoneParams(dot_shape=DOT_SQUARE, stochastic=1.0, angle=0.0,
                        frequency=1000.0 / cell, resolution=1000.0)
    d_square = _dot_metric(p2, cell, 0, cell, cell)

    thr = np.percentile(d_cross, 30.0)
    mask = d_cross <= thr
    ys, xs = np.nonzero(mask)
    assert xs.size > 0
    sub = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    cross_fill = float(sub.mean())

    thr2 = np.percentile(d_square, 30.0)
    mask2 = d_square <= thr2
    ys2, xs2 = np.nonzero(mask2)
    sub2 = mask2[ys2.min():ys2.max() + 1, xs2.min():xs2.max() + 1]
    square_fill = float(sub2.mean())

    assert square_fill > 0.999, f"方形外接矩形應填滿，實測 {square_fill:.3f}"
    assert cross_fill < 0.80, f"十字架四角應留白，實測填滿度 {cross_fill:.3f}"


def test_ink_range_semantics():
    """min_ink 決定最淡墨點，max_ink 決定最濃墨點，名實必須相符。"""
    img = np.concatenate([np.full((160, 160), 1.0, np.float32),
                          np.zeros((160, 160), np.float32)], axis=1)
    # 完全放開：純白無墨、純黑實心
    r = halftone(img, _flat(dot_gain=0.0))
    assert float((r[:, :160] == 0).mean()) == 0.0, "純白區不該有墨"
    assert float((r[:, 160:] == 0).mean()) > 0.97, "純黑區應近實心"

    # 下限提高 -> 高光開始出現墨點
    r = halftone(img, _flat(dot_gain=0.0, min_ink=0.20))
    assert 0.18 < float((r[:, :160] == 0).mean()) < 0.22

    # 上限降低 -> 暗部不再實心
    r = halftone(img, _flat(dot_gain=0.0, max_ink=0.70))
    assert 0.68 < float((r[:, 160:] == 0).mean()) < 0.72


def test_min_dot_filter_discards_small_dots():
    """最小墨點過濾：過小的墨點必須整個捨棄、留白。

    與 min_ink 方向相反：min_ink 把墨點**撐大**到下限，
    過濾則把過小的墨點**丟掉**，寧可留白也不印碎點。
    """
    img = np.full((300, 300), 0.90, dtype=np.float32)
    base = dict(dot_gain=0.0, frequency=40.0, resolution=750.0,
                stochastic=1.0, angle=0.0)

    r = halftone(img, _flat(**base))
    ink = float((r == 0).mean())
    assert 0.08 < ink < 0.12, f"基準上墨率應約 0.10，實測 {ink:.3f}"

    d = 2.0 * (25.4 / 40.0) * math.sqrt(ink / math.pi)
    r = halftone(img, _flat(filter_mm=d * 0.9, **base))
    assert float((r == 0).mean()) > 0.9 * ink, "門檻較小時不該丟棄"

    r = halftone(img, _flat(filter_mm=d * 1.1, **base))
    assert float((r == 0).mean()) == 0.0, "過小的墨點應完全留白"


def test_min_dot_filter_beats_ink_floor():
    """過濾優先級高於下限：下限撐大的墨點，只要仍小於門檻就照樣丟棄。"""
    img = np.full((300, 300), 0.90, dtype=np.float32)
    base = dict(dot_gain=0.0, frequency=40.0, resolution=750.0,
                stochastic=1.0, angle=0.0)
    pitch = 25.4 / 40.0

    # 下限 30 % 會把每個格子都撐到 30 % 墨量
    r = halftone(img, _flat(min_ink=0.30, **base))
    assert float((r == 0).mean()) > 0.2, "下限本身應有效果"

    # 門檻必須超過「被下限撐大後」的直徑，否則本來就不該被丟
    d_floor = 2.0 * pitch * math.sqrt(0.30 / math.pi)
    r = halftone(img, _flat(min_ink=0.30, filter_mm=d_floor * 1.05,
                            **base))
    assert float((r == 0).mean()) == 0.0, "過濾必須優先於下限"

    # 門檻低於撐大後的直徑時，下限仍然生效
    r = halftone(img, _flat(min_ink=0.30, filter_mm=d_floor * 0.9,
                            **base))
    assert float((r == 0).mean()) > 0.2, "門檻較小時下限應保留"


def test_filter_zero_means_disabled():
    img = np.full((200, 200), 0.88, dtype=np.float32)
    a = halftone(img, _flat(dot_gain=0.0, frequency=40.0, resolution=750.0))
    b = halftone(img, _flat(dot_gain=0.0, frequency=40.0, resolution=750.0,
                            filter_mm=0.0))
    assert np.array_equal(a, b)


def test_physical_metrics():
    """實體數值推算：印刷寬度決定 dpi，lpi 決定間距。"""
    p = HalftoneParams(print_width_mm=152.4, frequency=40.0,
                       resolution=4500.0 / 6.0)
    m = physical_metrics(p)
    assert abs(m["dpi"] - 750.0) < 1.0
    assert abs(m["pitch_mm"] - 25.4 / 40.0) < 1e-6
    # 圓形墨點 50% 覆蓋率 -> 直徑 = 2 * 間距 * sqrt(0.5/pi)
    want = 2.0 * m["pitch_mm"] * math.sqrt(0.5 / math.pi)
    assert abs(m["mid_mm"] - want) < 1e-9

    # 印刷寬度加倍（圖片不變）-> dpi 減半，墨點像素尺寸跟著減半
    p2 = HalftoneParams(print_width_mm=304.8, frequency=40.0,
                        resolution=4500.0 / 12.0)
    m2 = physical_metrics(p2)
    assert abs(m2["pitch_mm"] - m["pitch_mm"]) < 1e-9      # 物理間距不變
    assert m2["mid_px"] < m["mid_px"]                     # 但像素變小


def test_stochastic_changes_structure():
    """隨機網占比必須改變網點結構。"""
    img = np.full((200, 200), 0.5, dtype=np.float32)
    ordered = halftone(img, _flat(stochastic=1.0))
    random = halftone(img, _flat(stochastic=0.0))
    assert _difference(ordered, random) > 10.0


def test_seed_changes_random_pattern():
    """隨機種子必須改變隨機顆粒的分佈。"""
    img = np.full((200, 200), 0.5, dtype=np.float32)
    a = halftone(img, _flat(stochastic=0.0, seed=1))
    b = halftone(img, _flat(stochastic=0.0, seed=2))
    assert _difference(a, b) > 10.0


def test_seed_deterministic():
    """同一種子必須產生相同輸出。"""
    img = np.full((200, 200), 0.5, dtype=np.float32)
    a = halftone(img, _flat(seed=42))
    b = halftone(img, _flat(seed=42))
    assert np.array_equal(a, b)


def test_angle_changes_orientation():
    """網屏角度必須改變網格方向。"""
    img = np.full((200, 200), 0.5, dtype=np.float32)
    a = halftone(img, _flat(angle=0.0, stochastic=1.0))
    b = halftone(img, _flat(angle=45.0, stochastic=1.0))
    assert _difference(a, b) > 10.0


# ── 參數驗證 ────────────────────────────────────
def test_invalid_params_rejected():
    """非法參數必須被拒絕。"""
    img = np.full((64, 64), 0.5, dtype=np.float32)
    for kw in (dict(frequency=0.0), dict(stochastic=1.5),
               dict(min_ink=0.9, max_ink=0.1), dict(dot_shape=99),
               dict(noise_size=4), dict(print_width_mm=0.0)):
        try:
            halftone(img, HalftoneParams(**kw))
        except ValueError:
            continue
        raise AssertionError(f"參數未被拒絕：{kw}")


def test_empty_image_rejected():
    """空影像必須被拒絕。"""
    try:
        halftone(np.zeros((0, 0), dtype=np.float32), _flat())
    except ValueError:
        return
    raise AssertionError("空影像未被拒絕")


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")

    print(f"\n{len(tests) - failed}/{len(tests)} 通過")
    sys.exit(1 if failed else 0)
