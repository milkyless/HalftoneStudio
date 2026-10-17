"""影像讀寫與元資料處理。

設計原則
--------
讀入時只取「可見的像素資料」：會依 EXIF Orientation 轉正（否則顯示
方向會錯），其餘 EXIF、相機資訊、GPS、ICC 描述檔、縮圖預覽等一律丟棄，
絕不帶入處理流程。

輸出時另存新檔，同樣只寫入像素資料，不寫入任何 EXIF 或文字區塊。

關於 JPG
--------
JPEG 是有損壓縮：純黑白的網點邊緣存檔後會出現灰階雜訊。
若要拿去實際製版請使用 PNG（無損）。
程式仍提供 JPG 選項，並以最高畫質（quality=100、4:4:4 無色度抽樣）
把失真降到最低。

僅依賴 Pillow 與 NumPy，不涉及任何外部影像軟體。
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageOps

__all__ = [
    "load_image", "load_image_rgb", "save_image", "image_format_of",
    "ImageError", "PREVIEW_MAX_EDGE", "OUTPUT_FILTER", "is_lossy_format",
]

# 預覽用的長邊上限，避免超大影像拖慢介面
PREVIEW_MAX_EDGE = 1400

# 另存新檔時的檔案類型篩選字串
OUTPUT_FILTER = ("PNG 影像（無損，建議） (*.png);;"
                 "JPEG 影像（有損壓縮） (*.jpg *.jpeg);;"
                 "所有檔案 (*.*)")


class ImageError(Exception):
    """影像讀寫失敗時拋出。"""


# ── 讀入：只取可見像素 ──────────────────────────
def _open_visible(path: str) -> Image.Image:
    """開啟影像並依 EXIF Orientation 轉正。

    EXIF 僅用於修正方向，轉成獨立影像後即與其脫鉤，
    其餘中繼資料一概不取。
    """
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            return im.copy()          # 脫離原檔案，中繼資料不再相連
    except ImageError:
        raise
    except Exception as exc:
        raise ImageError(f"無法讀取影像：{exc}") from exc


def _resize(img: Image.Image, max_edge: int | None) -> Image.Image:
    if not max_edge:
        return img
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img
    scale = max_edge / longest
    return img.resize((max(1, round(w * scale)),
                       max(1, round(h * scale))),
                      Image.LANCZOS)


def load_image(path: str, max_edge: int | None = None) -> np.ndarray:
    """讀入影像並轉為灰階 float32 陣列（0..1，0 = 黑）。

    參數 max_edge 指定時，會等比例縮小使長邊不超過該值。
    回傳值只有像素資料，不含任何中繼資料。
    """
    with _open_visible(path) as img:
        with img.convert("L") as gray:
            arr = np.asarray(_resize(gray, max_edge), dtype=np.uint8)

    if arr.size == 0:
        raise ImageError("影像內容為空")
    return arr.astype(np.float32) / 255.0


def load_image_rgb(path: str, max_edge: int | None = None) -> np.ndarray:
    """讀入影像並轉為 RGB uint8 陣列，供介面預覽原始色彩使用。"""
    with _open_visible(path) as img:
        with img.convert("RGB") as rgb:
            arr = np.asarray(_resize(rgb, max_edge), dtype=np.uint8)

    if arr.size == 0:
        raise ImageError("影像內容為空")
    return arr


# ── 輸出：另存新檔，只寫像素 ────────────────────
def image_format_of(path: str) -> str:
    """依副檔名判斷輸出格式，未支援者一律視為 PNG。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".jpe"):
        return "JPEG"
    return "PNG"


def is_lossy_format(fmt: str) -> bool:
    """該格式是否為有損壓縮。"""
    return fmt.upper() in ("JPEG", "JPG")


def save_image(array: np.ndarray, path: str, quality: int = 100) -> str:
    """將 (H, W) 的 uint8 陣列另存新檔。

    只寫入可見像素資料：不附加 EXIF、文字區塊或任何中繼資料。

    PNG 以 1-bit（雙色）輸出 —— 半調結果本來就是純黑白，
    1-bit 體積最小（約為 8 位元灰階的 1/8），且不會有任何灰階鋸齒。
    JPEG 為格式限制，只能用 8 位元灰階。

    回傳實際寫入的檔案格式（'PNG' 或 'JPEG'）。
    """
    if array.ndim != 2:
        raise ImageError("輸出必須是 (H, W) 的二維灰階陣列")
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)

    fmt = image_format_of(path)
    base = Image.fromarray(array, mode="L")

    # 明確指定 format，且不傳入任何 pnginfo / exif，
    # 確保輸出檔案不含中繼資料。
    try:
        if fmt == "JPEG":
            base.save(path, format="JPEG",
                      quality=max(1, min(100, quality)),
                      subsampling=0,      # 4:4:4，不做色度抽樣
                      optimize=True,
                      exif=b"")           # 明確清空 EXIF
        else:
            # 1-bit 雙色：不做抖動，只做門檻化。
            # 輸出已是純 0/255，因此門檻化不會損失任何資訊。
            bilevel = base.convert("1", dither=Image.NONE)
            bilevel.save(path, format="PNG",
                         optimize=True,
                         bits=1,
                         pnginfo=None)    # 明確不寫入文字區塊
    except Exception as exc:
        raise ImageError(f"無法寫入影像：{exc}") from exc

    return fmt

