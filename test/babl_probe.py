"""確認 babl 格式名稱是否有效。

重點：Gegl.Buffer.get() 回傳的 list，其元素型別決定拿到的是
      位元組還是正規化浮點數。本檔只驗證格式名稱是否被接受。
"""
import gi

gi.require_version('Babl', '0.1')
gi.require_version('Gegl', '0.4')
from gi.repository import Babl, Gegl

Gegl.init(None)

print('--- Babl 模組可用性 ---')
print('Babl 內容:', [x for x in dir(Babl) if x[0].isupper()])

names = ["R'G'B'A float", "R'G'B' float", 'RGBA float', 'RGB float',
         'R"g"b"a float', 'YA float', 'Y float']

print()
print('--- 嘗試建立格式 ---')
for n in names:
    try:
        fmt = Babl.Formats.new(n)
        print('  OK      %-18s -> %s' % (n, fmt))
    except Exception as e:
        print('  FAIL    %-18s | %s: %s' % (n, type(e).__name__, e))

