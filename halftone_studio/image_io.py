"""影像讀寫與灰階轉換。

僅依賴 Pillow 與 NumPy，不涉及任何外部影像軟體。
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

__all__ = ["load_image", "save_png", "SUPPORTED_INPUT", "SUPPORTED_OUTPUT"]

SUPPORTED_INPUT = (
    "*.jpg", "*.jpeg", "*.JPG", "*.JPEG", "*.png", "*.PNG",
)
SUPPORTED_OUTPUT = "PNG 影像 (*.png)"

# 預覽用的長邊上限，避免超大影像拖慢介面
PREVIEW_MAX_EDGE = 1400


class ImageLoadError(Exception):
    """影像無法讀取時拋出。"""


def load_image(path: str, max_edge: int | None = None) -> np.ndarray:
    """讀取影像並轉為灰階 float32 陣列（0..1，0 = 黑）。

    參數 max_edge 指定時，會等比例縮小使長邊不超過該值。
    """
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("L")

            if max_edge:
                w, h = im.size
                longest = max(w, h)
                if longest > max_edge:
                    scale = max_edge / longest
                    new = (max(1, int(round(w * scale))),
                           max(1, int(round(h * scale))))
                    im = im.resize(new, Image.LANCZOS)

            arr = np.asarray(im, dtype=np.uint8)
    except ImageLoadError:
        raise
    except Exception as exc:
        raise ImageLoadError(f"無法讀取影像：{exc}") from exc

    if arr.size == 0:
        raise ImageLoadError("影像內容為空")

    return (arr.astype(np.float32) / 255.0)


def save_png(array: np.ndarray, path: str) -> None:
    """將 (H, W) 的 uint8 陣列存成 PNG。

    以 L 模式輸出，確保是真正的 8 位元灰階（黑墨白底），
    不會因為 RGB 轉換而讓邊緣出現灰階鋸齒。
    """
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    Image.fromarray(array, mode="L").save(path, format="PNG",
                                          optimize=True)
