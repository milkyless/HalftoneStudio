"""驗證：輸入只取可見像素，輸出另存新檔且不含任何中繼資料。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from halftone_studio.core import DOT_ORGANIC, HalftoneParams, halftone
from halftone_studio.image_io import (
    load_image, load_image_rgb, save_image,
)

SRC = "docs/meta_test.jpg"


def build_source() -> None:
    """建立帶有完整中繼資料的測試 JPG。"""
    exif = Image.Exif()
    exif[0x010F] = "Canon"                    # 製造商
    exif[0x0110] = "EOS R5"                   # 型號
    exif[0x0132] = "2024:05:01 10:30:00"      # 拍攝時間
    exif[0x013B] = "Photographer"             # 創作者
    exif[0x8298] = "Copyright Secret"         # 版權
    exif[0x010E] = "ImageDescription"         # 描述
    exif[0x9286] = "UserComment"              # 註解

    s = 400
    yy, xx = np.mgrid[0:s, 0:s]
    a = np.zeros((s, s, 3), dtype=np.uint8)
    a[..., 0] = (127 + 110 * np.sin(xx / 30)).astype(np.uint8)
    a[..., 1] = (127 + 110 * np.cos(yy / 25)).astype(np.uint8)
    a[..., 2] = ((xx + yy) / (2 * s) * 255).astype(np.uint8)

    Image.fromarray(a).save(SRC, quality=92, exif=exif,
                           dpi=(300, 300), comment=b"SECRET COMMENT")


def main() -> int:
    build_source()

    src = Image.open(SRC)
    print("=== 來源檔 ===")
    print("  EXIF 標記數 :", len(src.getexif()))
    print("  相機 / 型號 :", src.getexif().get(0x010F),
          "/", src.getexif().get(0x0110))
    print("  版權        :", src.getexif().get(0x8298))
    print("  JPEG 註解   :", src.info.get("comment"))
    print("  info keys   :", sorted(src.info.keys()))
    src.close()

    size_before = os.path.getsize(SRC)
    mtime_before = os.path.getmtime(SRC)

    gray = load_image(SRC)
    color = load_image_rgb(SRC)
    print("\n=== 讀入結果（只有像素）===")
    print("  灰階 :", gray.shape, gray.dtype)
    print("  彩色 :", color.shape, color.dtype)

    result = halftone(gray, HalftoneParams(dot_shape=DOT_ORGANIC,
                                           stochastic=0.15))

    ok = True
    print("\n=== 輸出檢查 ===")
    for out in ("docs/out_test.png", "docs/out_test.jpg"):
        fmt = save_image(result, out)
        im = Image.open(out)
        exif_count = len(im.getexif())
        keys = sorted(k for k in im.info if k != "jfif")
        print(f"  {fmt:4s} -> {os.path.basename(out)} "
              f"({os.path.getsize(out)} bytes)")
        print(f"         mode={im.mode}  EXIF={exif_count}  "
              f"其他中繼資料={keys or '無'}")

        # PNG 必須完全無損且零中繼資料
        if fmt == "PNG":
            if exif_count or keys:
                print("         [失敗] PNG 仍帶有中繼資料")
                ok = False
            back = np.asarray(Image.open(out))
            if not np.array_equal(back, result):
                print("         [失敗] PNG 像素與原始結果不符")
                ok = False
            else:
                print("         [通過] 像素完全一致（無損）")

        # JPEG 為有損，但格式與灰階必須正確
        else:
            back = np.asarray(Image.open(out))
            gray_levels = len(np.unique(back))
            print(f"         [注意] 有損壓縮，灰階種類 {gray_levels} 種"
                  f"（原始為 2 種）")
            if im.mode != "L":
                print("         [失敗] 應為灰階影像")
                ok = False
            if "comment" in im.info:
                print("         [失敗] JPEG 註解未被清除")
                ok = False
        im.close()

    print("\n=== 原檔保護 ===")
    unchanged_size = os.path.getsize(SRC) == size_before
    unchanged_mtime = os.path.getmtime(SRC) == mtime_before
    print("  大小未變 :", unchanged_size)
    print("  異動時間未變 :", unchanged_mtime)
    if not (unchanged_size and unchanged_mtime):
        ok = False

    print("\n結果：", "全部通過" if ok else "有項目失敗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
