"""演算法測試。

執行方式：
    .venv\\Scripts\\python.exe -m pytest tests -v
或直接：
    .venv\\Scripts\\python.exe tests\\test_core.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from halftone_studio.blue_noise import generate_blue_noise  # noqa: E402
from halftone_studio.core import (  # noqa: E402
    DOT_ORGANIC, DOT_ROUND, DOT_SQUARE, HalftoneParams, halftone,
    to_grayscale,
)


def _flat(**kw) -> HalftoneParams:
    """不含夾限與擴大的參數，便於檢驗密度還原。"""
    base = dict(min_dot=0.0, max_dot=1.0, dot_gain=0.0)
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


def test_grain_scale_affects_size():
    """顆粒粗細必須實際改變輸出。"""
    img = np.full((200, 200), 0.5, dtype=np.float32)
    ref = halftone(img, _flat())
    big = halftone(img, _flat(grain_scale=3.0))
    assert _difference(ref, big) > 10.0


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
               dict(min_dot=0.9, max_dot=0.1), dict(dot_shape=99),
               dict(noise_size=4)):
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
