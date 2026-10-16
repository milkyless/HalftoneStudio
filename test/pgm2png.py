"""將 PGM (P5) 轉成 PNG，並裁切放大局部以檢視網點結構。

用法：python pgm2png.py <輸入.pgm> <輸出.png> [放大倍率] [裁切x] [裁切y] [裁切w] [裁切h]
"""
import struct
import sys
import zlib


def read_pgm(path):
    with open(path, "rb") as fh:
        data = fh.read()

    # 解析 P5 標頭（支援註解）
    tokens, pos = [], 2
    while len(tokens) < 3:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            while data[pos:pos + 1] not in (b"\n", b""):
                pos += 1
            continue
        start = pos
        while not data[pos:pos + 1].isspace():
            pos += 1
        tokens.append(int(data[start:pos]))
    pos += 1

    w, h, _maxval = tokens
    return w, h, data[pos:pos + w * h]


def write_png(path, w, h, pixels):
    raw = b"".join(b"\x00" + bytes(pixels[y * w:(y + 1) * w]) for y in range(h))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")

    with open(path, "wb") as fh:
        fh.write(png)


def crop_zoom(src, w, h, zoom, cx, cy, cw, ch):
    ow, oh = cw * zoom, ch * zoom
    out = bytearray(ow * oh)
    for y in range(oh):
        sy = cy + y // zoom
        for x in range(ow):
            sx = cx + x // zoom
            out[y * ow + x] = src[sy * w + sx] if 0 <= sx < w and 0 <= sy < h else 0
    return ow, oh, out


def main():
    src_path, out_path = sys.argv[1], sys.argv[2]
    zoom = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    cx = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    cy = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    cw = int(sys.argv[6]) if len(sys.argv) > 6 else 0
    ch = int(sys.argv[7]) if len(sys.argv) > 7 else 0

    w, h, pixels = read_pgm(src_path)

    if zoom > 1 and cw > 0:
        w, h, pixels = crop_zoom(pixels, w, h, zoom, cx, cy, cw, ch)
    elif zoom > 1:
        w, h, pixels = crop_zoom(pixels, w, h, zoom, 0, 0, w // 2, h // 2)

    write_png(out_path, w, h, pixels)
    print(f"{out_path}  {w}x{h}")


if __name__ == "__main__":
    raise SystemExit(main())
