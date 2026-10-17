"""诊断：密度误差随灰阶的变化，定位误差来源。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from halftone_studio.core import HalftoneParams, halftone

header = f"{'tone':>6} {'target':>9} {'actual':>9} {'error':>9}"
for st in (0.0, 1.0):
    print(f"--- stochastic={st}  圆形 ---")
    print(header)
    for lv in (0.02, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.98):
        g = np.full((160, 160), lv, dtype=np.float32)
        p = HalftoneParams(min_ink=0.0, max_ink=1.0, dot_gain=0.0,
                           stochastic=st)
        ink = float((halftone(g, p) == 0).mean())
        print(f"{lv:6.2f} {1-lv:9.4f} {ink:9.4f} {ink-(1-lv):+9.4f}")
    print()
