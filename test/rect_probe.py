"""驗證 Gegl.Rectangle 的屬性賦值在 Python 綁定下是否真的生效。

若 rect.x/.y/.width/.height 無法寫入，rect 會維持全 0，
導致 buffer.get 取不到資料、buffer.set 什麼都沒寫入。
"""
import gi

gi.require_version('Gegl', '0.4')
from gi.repository import Gegl

Gegl.init(None)

print('Rectangle 可用屬性 :',
      [x for x in dir(Gegl.Rectangle) if x in ('x', 'y', 'width', 'height')])
print('Rectangle 可用方法 :',
      [x for x in dir(Gegl.Rectangle) if not x.startswith('_')
       and callable(getattr(Gegl.Rectangle, x, None))][:10])

r = Gegl.Rectangle()
print('新建後 : x=%s y=%s w=%s h=%s'
      % (r.x, r.y, r.width, r.height))

r.x = 10
r.y = 20
r.width = 100
r.height = 50
print('賦值後 : x=%s y=%s w=%s h=%s' % (r.x, r.y, r.width, r.height))
print('賦值是否生效 :', r.x == 10 and r.y == 20 and
      r.width == 100 and r.height == 50)

print()
print('--- 若上面「賦值是否生效」為 False，代表外掛的 rect 全是 0，')
print('    buffer.get 取不到資料、buffer.set 不寫入，影像自然完全沒變化。')
