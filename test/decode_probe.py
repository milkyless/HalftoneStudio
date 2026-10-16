"""驗證 array 解碼邏輯：位元組 → 浮點數。

確認 16 個位元組確實對應 4 通道 float32，且解碼後數值合理。
"""
import array
import struct

# 兩個像素、4 通道 float32：小灰階(0.25) 與大灰階(0.75)
floats = [0.25, 0.25, 0.25, 1.0,
          0.75, 0.75, 0.75, 1.0]
raw = array.array('f', floats).tobytes()

print('位元組長度 :', len(raw), '（預期 16）')
print('前 8 個位元組:', list(raw[:8]))

back = array.array('f', raw)
print('解碼後 :', [round(v, 4) for v in back])
print('解碼正確 :', all(abs(a - b) < 1e-6 for a, b in zip(floats, back)))

print()
print('--- 長度推斷規則 ---')
print('16 個位元組 / 4 bytes = %d 通道 (RGBA)' % (16 // 4))
print('12 個位元組 / 4 bytes = %d 通道 (RGB)' % (12 // 4))
print('3 或 4 個值            → 已由 GEGL 轉為浮點數')

print()
print('--- 效能：array 解碼 6000x32 像素 ---')
import time
n = 6000 * 32 * 4
big = array.array('f', [0.5] * n).tobytes()
t0 = time.time()
dec = array.array('f', big)
el = time.time() - t0
print('解碼 %d 個浮點數耗時 %.3f 秒' % (n, el))
print('單純解碼已是 %.1f 萬像素/秒的上限' % (6000 * 32 / el / 10000))
