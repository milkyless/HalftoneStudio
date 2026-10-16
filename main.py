"""啟動入口。

用法：
    .venv\\Scripts\\python.exe main.py
"""
from __future__ import annotations

import sys

from halftone_studio.app import main

if __name__ == "__main__":
    sys.exit(main())
