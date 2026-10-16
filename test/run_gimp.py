"""執行 gimp-console 並把輸出正確解碼成 UTF-8。

用法：python run_gimp.py [輸出檔] [scm 檔名]
"""
import os
import subprocess
import sys

GIMP = r"D:\Software\GIMP 3\bin\gimp-console-3.2.exe"
SCRIPTS = r"C:\Users\Milky\Desktop\Z\test"


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "cp950", "cp1252"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if "�" not in text:
            return text
    return raw.decode("utf-8", errors="replace")


def main() -> int:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "gimp_log.txt"
    scm_name = sys.argv[2] if len(sys.argv) > 2 else "run_test.scm"
    scm_path = os.path.join(SCRIPTS, scm_name).replace("\\", "/")

    cmd = [GIMP, "-id", "--verbose",
           "--batch-interpreter", "plug-in-script-fu-eval",
           "-b", '(load "%s")' % scm_path,
           "-b", "(gimp-quit 0)"]

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=240)
        raw = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or b"") + (exc.stderr or b"")
        raw += b"\n*** TIMEOUT ***\n"

    text = decode(raw)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)

    print(f"wrote {out_path} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())