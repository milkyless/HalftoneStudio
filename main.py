"""啟動入口。

用法：
    .venv\\Scripts\\python.exe main.py

打包成單檔 exe 時，若未預期的例外發生，使用者仍會看到
明確的錯誤訊息，而不會視窗無聲地關閉。
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
import tempfile
import time
import traceback

# 早於這個時間的 _MEI 目錄才視為殘留。
#
# PyInstaller 單檔 exe 會解壓到 %TEMP%\_MEIxxxxxx（約 149 MB）。
# 正常關閉時 bootloader 會自行刪除；只有被工作管理員強制結束時才會
# 留下垃圾。
#
# 取 24 小時是為了絕對安全：使用者可能同時開著另一個實例，那個
# 目錄一定不到 24 小時，不會被誤刪。
STALE_MEI_AGE = 24 * 3600


def purge_stale_meipass(age_seconds: float = STALE_MEI_AGE,
                        temp_dir: str | None = None) -> list[str]:
    """清掉先前殘留的 _MEI 解壓目錄，回傳實際刪除的路徑。

    早期實作是在退出時啟動 `cmd /c "ping -n 4 127.0.0.1 & rmdir ..."`
    等本行程結束再刪。兩個問題：

      1. `ping` 是在本機回送地址，不是對外連線，但使用者在畫面上
         會看到黑色終端視窗不斷回應封包，誤以為程式在連網。
      2. `CREATE_NO_WINDOW` 與 `DETACHED_PROCESS` 互相衝突
         （MSDN 明確註明兩者不可併用），視窗仍會被開出來。

    改成啟動時清理，就不需要任何子行程，自然也不會有終端視窗。
    只刪「已經很舊且刪得掉」的目錄；刪不掉（仍被某個實例佔用）
    就安靜略過，任何失敗都不影響程式啟動。
    """
    removed: list[str] = []

    # 本行程正在使用的目錄，絕不能碰
    mine = getattr(sys, "_MEIPASS", None)

    root = temp_dir or tempfile.gettempdir()
    now = time.time()
    for path in glob.glob(os.path.join(root, "_MEI*")):
        try:
            if not os.path.isdir(path) or os.path.islink(path):
                continue
            if mine and os.path.abspath(path) == os.path.abspath(mine):
                continue
            if now - os.path.getmtime(path) < age_seconds:
                continue
            shutil.rmtree(path)
            removed.append(path)
        except OSError:
            # 仍被占用或權限不足，略過即可
            continue
    return removed


def _report_fatal(exc: BaseException) -> None:
    """以對話框顯示致命錯誤。"""
    detail = "".join(traceback.format_exception(type(exc), exc,
                                               exc.__traceback__))
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("程式啟動失敗")
        box.setText("Halftone Studio 啟動時發生錯誤。\n\n"
                    f"{type(exc).__name__}: {exc}")
        box.setDetailedText(detail)
        box.exec()
    except Exception:  # noqa: BLE001
        # 連對話框都無法顯示時，至少把訊息寫到 stderr
        print(detail, file=sys.stderr)


def _selftest() -> int:
    """自我檢測：驗證打包後的環境能完整運作。

    以 --selftest 參數觸發。會實際建立視窗、載入影像、執行半調
    並輸出檔案，把結果寫入 --selftest 指定的路徑。
    用於確認打包排除模組後功能依然完整。
    """
    import os
    import tempfile

    out_path = None
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        if i + 1 < len(sys.argv):
            out_path = sys.argv[i + 1]

    lines: list[str] = []
    code = 0
    try:
        import numpy as np
        from PIL import Image

        from halftone_studio.app import MainWindow
        from halftone_studio.core import DOT_ORGANIC, HalftoneParams, halftone
        from halftone_studio.image_io import load_image, save_image
        from halftone_studio.theme import get_stylesheet

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication(sys.argv[:1])
        app.setStyle("Fusion")
        app.setStyleSheet(get_stylesheet())
        lines.append("Qt 初始化：成功")

        win = MainWindow()
        lines.append("主視窗建立：成功")

        # ── 版面診斷 ────────────────────────────────────
        # 打包後曾出現右側控制面板整片消失的情況，
        # 這裡把實際幾何資訊寫出來以便比對。
        from PySide6.QtWidgets import QSplitter
        win.resize(1613, 1013)
        win.show()
        app.processEvents()
        lines.append(f"視窗尺寸：{win.width()} x {win.height()}")

        sps = win.findChildren(QSplitter)
        lines.append(f"splitter 數量：{len(sps)}")
        for sp in sps:
            lines.append(f"  面板尺寸：{sp.sizes()}")
            for i in range(sp.count()):
                wd = sp.widget(i)
                lines.append(
                    f"    面板{i} 可見={wd.isVisible()} "
                    f"尺寸={wd.width()}x{wd.height()} "
                    f"最小寬={wd.minimumSizeHint().width()}")
        lines.append(f"開啟按鈕可見：{win.btn_open.isVisible()} "
                     f"寬={win.btn_open.width()}")
        lines.append(f"形狀下拉可見：{win.cmb_shape.isVisible()} "
                     f"寬={win.cmb_shape.width()}")

        # 由程式自己渲染元件樹存圖：grab() 不依賴螢幕擷取，
        # 能確實反映打包後的繪製結果。
        if out_path:
            shot = os.path.splitext(out_path)[0] + "_ui.png"
            try:
                win.grab().save(shot)
                lines.append(f"介面截圖：成功 {shot}")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"介面截圖失敗：{exc}")

        tmpdir = tempfile.mkdtemp(prefix="halftone_selftest_")
        src = os.path.join(tmpdir, "input.jpg")

        s = 256
        yy, xx = np.mgrid[0:s, 0:s]
        a = np.zeros((s, s, 3), dtype=np.uint8)
        a[..., 0] = (127 + 110 * np.sin(xx / 20)).astype(np.uint8)
        a[..., 1] = (127 + 110 * np.cos(yy / 18)).astype(np.uint8)
        a[..., 2] = ((xx + yy) / (2 * s) * 255).astype(np.uint8)
        Image.fromarray(a).save(src, quality=92)
        lines.append("建立測試影像：成功")

        gray = load_image(src)
        color = np.asarray(Image.fromarray(a))
        lines.append(f"載入 JPG：成功 {gray.shape}")

        result = halftone(gray, HalftoneParams(dot_shape=DOT_ORGANIC,
                                               stochastic=0.2))
        levels = len(np.unique(result))
        ink = float((result == 0).mean())
        lines.append(f"半調運算：成功 灰階種類={levels} 上墨率={ink:.3f}")

        for name, ext in (("out.png", ".png"), ("out.jpg", ".jpg")):
            fmt = save_image(result, os.path.join(tmpdir, name))
            check = np.asarray(Image.open(os.path.join(tmpdir, name)))
            lines.append(f"輸出 {fmt}：成功 {check.shape}")

        win.close()
        app.processEvents()
        lines.append("RESULT=OK")
    except Exception as exc:  # noqa: BLE001
        import traceback
        lines.append(f"RESULT=FAIL {type(exc).__name__}: {exc}")
        lines.append(traceback.format_exc())
        code = 1

    text = "\n".join(lines)
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError:
            pass
    if sys.stdout is not None:
        try:
            print(text)
        except Exception:  # noqa: BLE001
            pass
    return code


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    from halftone_studio.app import main as run
    return run()



if __name__ == "__main__":
    # 清理先前殘留的解壓目錄。不啟動任何子行程，因此不會出現
    # 黑色終端視窗。
    try:
        purge_stale_meipass()
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        _report_fatal(exc)
        sys.exit(1)

