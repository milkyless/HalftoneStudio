"""不依賴 GIMP，驗證網點演算法本身的正確性與速度。

讀入外掛模組中的純演算法函式，以合成灰階影像測試：
  1. 灰階遞增時上墨率應單調遞增
  2. 各灰階下的實際上墨率應接近目標值
  3. 實測處理速度
"""
import importlib.util
import time

PLUGIN = (r'C:\Users\Milky\AppData\Roaming\GIMP\3.2'
          r'\plug-ins\zh-halftone-test\zh-halftone-test.py')

src = open(PLUGIN, encoding='utf-8').read()
# 去掉最後一行 Gimp.main，避免啟動事件迴圈
src = src.replace('Gimp.main(ZhHalftoneTest.__gtype__, sys.argv)', 'pass')

ns = {'__name__': 'algo'}
exec(compile(src, PLUGIN, 'exec'), ns)

build_screen_tile = ns['build_screen_tile']
halftone_strip = ns['halftone_strip']
analyse_strip = ns['analyse_strip']
solve_bias = ns['solve_bias']
HIST_BINS = ns['HIST_BINS']
RESOLUTION = ns['RESOLUTION']
FREQUENCY = ns['FREQUENCY']
ANGLE = ns['ANGLE']


def make_flat(width, height, level):
    data = []
    for _ in range(width * height):
        data.extend([level, level, level, 1.0])
    return data


def run_with_calibration(width, height, level, tile, tw, th):
    """比照外掛的兩趟流程。"""
    data = make_flat(width, height, level)

    # 第一趟：直方圖 + 實際上墨數
    hist = [0] * HIST_BINS
    ink_counter = [0]
    analyse_strip(data, hist, ink_counter, tile, tw, th, 0, width)

    total_px = width * height
    tone_sum = 0.0
    for i, c in enumerate(hist):
        if c:
            tone_sum += c * ((i + 0.5) / HIST_BINS)

    bias = solve_bias(ink_counter[0], total_px, tone_sum)

    # 第二趟：套用
    out = [0.0] * len(data)
    halftone_strip(data, out, width, height, 0, tile, tw, th, bias)

    ink = sum(1 for v in out[0::4] if v < 0.5) / total_px
    return ink, bias


cell = RESOLUTION / FREQUENCY
tile, tw, th = build_screen_tile(cell, ANGLE)

print('網距 cell = %.2f px，網屏磚 %dx%d' % (cell, tw, th))
print()

W, H = 128, 64
print('--- 灰階還原（黑墨白底：墨量應 = 1 - 灰階）---')
print('%-8s %-12s %-12s %-9s %s'
      % ('灰階', '目標墨量', '實際墨量', '誤差', '偏移'))
for level in (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95):
    ink, bias = run_with_calibration(W, H, level, tile, tw, th)
    target = 1.0 - level
    print('%-8.2f %-12.4f %-12.4f %+9.4f %+.4f'
          % (level, target, ink, ink - target, bias))

print()
print('--- 不同影像寬度，50% 灰（含密度校準）---')
worst = 0.0
for width in (61, 100, 137, 200, 400, 512, 600, 640, 720, 800, 1024,
              1200, 1500, 1920, 2048, 2400, 3000, 4000, 6000):
    ink, bias = run_with_calibration(width, 64, 0.5, tile, tw, th)
    err = ink - 0.5
    worst = max(worst, abs(err))
    print('  寬 %-5d 誤差 %+.4f  偏移 %+.4f%s'
          % (width, err, bias, '  <== 異常' if abs(err) > 0.01 else ''))

print()
print('最大誤差 %.4f' % worst)

print()
t0 = time.time()
rows = 32
for _ in range(10):
    n = W * rows * 4
    data = [0.5] * n
    out = [0.0] * n
    halftone_strip(data, out, W, rows, 0, tile, tw, th, 0.0)
el = time.time() - t0
px = W * rows * 10
print('速度：%.1f 萬像素/秒' % (px / el / 10000))
print('24 百萬像素單趟預估 %.1f 秒，兩趟約 %.1f 秒'
      % (24e6 / (px / el), 2 * 24e6 / (px / el)))

