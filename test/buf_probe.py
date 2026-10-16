"""實測 Gegl.Buffer 在 Python 綁定下的 get/set 行為。"""
import gi

gi.require_version('Gegl', '0.4')
from gi.repository import Gegl

Gegl.init(None)

FMT = "R'G'B'A float"

buf = Gegl.TempFile.new()
buf.set_extent(0, 0, 4, 2)

r = Gegl.Rectangle()
r.x, r.y, r.width, r.height = 0, 0, 4, 2

src = [0.5] * (4 * 2 * 4)
buf.set(r, FMT, src)

out = buf.get(r, 1.0, FMT, Gegl.AbyssPolicy.CLAMP)

print('回傳型別 :', type(out).__name__, '長度 =', len(out))
print('前 6 個值:', out[:6])

out[0] = 9.0
print('是否可變 :', out[0])

back = buf.get(r, 1.0, FMT, Gegl.AbyssPolicy.CLAMP)
print('回寫是否生效:', back[0])

print('AbyssPolicy :', [x for x in dir(Gegl.AbyssPolicy) if x.isupper()])
print('Buffer.flush:', Gegl.Buffer.flush.__doc__)
