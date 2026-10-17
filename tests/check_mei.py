"""驗證 _MEI 殘留清理，以及「不會再啟動 ping / cmd」。

背景：舊實作在啟動時執行
    cmd /c "ping -n 4 127.0.0.1 >nul & rmdir /s /q <_MEIPASS>"
使用者的畫面上會跳出黑色終端視窗並看到回環位址的 ping 回應，
誤以為程式在連網。現已改為啟動時自行清理，不啟動任何子行程。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main as entry                                        # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{extra}")
    if not cond:
        failures.append(label)


print("=== 1. 程式碼中不再有 ping / cmd / 子行程 ===")
# 不能用字串搜尋：說明舊做法的註解裡本來就會提到那些字樣。
# 改用 AST，只檢查真正會執行的程式碼（排除 docstring）。
import ast                                           # noqa: E402

tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))

docstrings = set()
for node in ast.walk(tree):
    if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                         ast.ClassDef)):
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            docstrings.add(id(body[0].value))

strings = [n.value for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and id(n) not in docstrings]
check("可執行字串中不含 ping", not any("ping" in s for s in strings),
      f"（{[s for s in strings if 'ping' in s]}）")
check("可執行字串中不含 cmd/rmdir",
      not any(("cmd" in s or "rmdir" in s) for s in strings),
      f"（{[s for s in strings if 'cmd' in s or 'rmdir' in s]}）")

imports = {a.name.split('.')[0] for n in ast.walk(tree)
           if isinstance(n, ast.Import) for a in n.names}
imports |= {n.module.split('.')[0] for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module}
check("未 import subprocess", "subprocess" not in imports,
      f"（imports: {sorted(imports)}）")

# 只有 attribute 形式的呼叫才可能是 subprocess.xxx（subprocess 是
# 模組，一律以屬性呼叫）；名稱形式的 run 是本地的 app.main，屬正常。
attr_calls = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
name_calls = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
launchers = {"Popen", "system", "popen", "run", "call",
             "check_output", "check_call"}
found = (launchers & attr_calls) | (launchers - {"run"} & name_calls)
check("沒有啟動子行程的呼叫", not found, f"（發現 {sorted(found)}）")

check("已移除 _schedule_meipass_cleanup",
      not hasattr(entry, "_schedule_meipass_cleanup"))
check("提供 purge_stale_meipass", hasattr(entry, "purge_stale_meipass"))

print("\n=== 2. 只刪舊目錄，新目錄保留 ===")
tmp = tempfile.mkdtemp(prefix="mei_test_")

# 建立一個「很舊的」目錄
old_dir = os.path.join(tmp, "_MEI00000001")
os.makedirs(os.path.join(old_dir, "sub"), exist_ok=True)
with open(os.path.join(old_dir, "sub", "x.dll"), "wb") as fh:
    fh.write(b"0" * 1024)
old_time = time.time() - 3 * 24 * 3600
os.utime(old_dir, (old_time, old_time))

# 建立一個「剛建立的」目錄（模擬另一個正在執行的實例）
new_dir = os.path.join(tmp, "_MEI00000002")
os.makedirs(new_dir, exist_ok=True)
with open(os.path.join(new_dir, "y.dll"), "wb") as fh:
    fh.write(b"0" * 1024)

# 不屬於 _MEI 的目錄，也必須不動
other_dir = os.path.join(tmp, "_MEI_NOTMATCH")
os.makedirs(other_dir + "_keep", exist_ok=True)

removed = entry.purge_stale_meipass(temp_dir=tmp)

check("舊的 _MEI 目錄已刪除", not os.path.exists(old_dir),
      f"（回傳 {len(removed)} 個）")
check("剛建立的 _MEI 目錄保留（不誤刪正在使用的）",
      os.path.isdir(new_dir))
check("回傳結果只含舊目錄", all("00000001" in r for r in removed),
      f"（{removed}）")

print("\n=== 3. 本行程自己的 _MEIPASS 絕不刪除 ===")
tmp2 = tempfile.mkdtemp(prefix="mei_self_")
self_dir = os.path.join(tmp2, "_MEIselfcheck")
os.makedirs(self_dir, exist_ok=True)
with open(os.path.join(self_dir, "z.dll"), "wb") as fh:
    fh.write(b"0" * 512)
old = time.time() - 5 * 24 * 3600
os.utime(self_dir, (old, old))

saved = getattr(sys, "_MEIPASS", None)
sys._MEIPASS = self_dir          # type: ignore[attr-defined]
try:
    entry.purge_stale_meipass(temp_dir=tmp2)
    check("自己的 _MEIPASS 未被刪除", os.path.isdir(self_dir))
finally:
    if saved is None:
        del sys._MEIPASS       # type: ignore[attr-defined]
    else:
        sys._MEIPASS = saved   # type: ignore[attr-defined]

print("\n=== 4. 邊界情況不得讓啟動失敗 ===")
try:
    entry.purge_stale_meipass(temp_dir=os.path.join(tmp, "not_exist"))
    check("不存在的目錄不拋例外", True)
except Exception as exc:  # noqa: BLE001
    check("不存在的目錄不拋例外", False, str(exc))

locked = os.path.join(tmp, "_MEIlocked")
os.makedirs(locked, exist_ok=True)
old = time.time() - 5 * 24 * 3600
os.utime(locked, (old, old))
# 用唯讀檔案鎖住，讓 rmtree 失敗（Windows 上）
probe = os.path.join(locked, "hold.txt")
with open(probe, "w", encoding="utf-8") as fh:
    fh.write("hold")
os.chmod(locked, 0o555)
try:
    entry.purge_stale_meipass(temp_dir=tmp)
    check("刪不掉時安靜略過", True)
except Exception as exc:  # noqa: BLE001
    check("刪不掉時安靜略過", False, str(exc))
os.chmod(locked, 0o755)

import shutil                                        # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(tmp2, ignore_errors=True)

print()
if failures:
    print(f"失敗 {len(failures)} 項：")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("全部通過")
sys.exit(0)
