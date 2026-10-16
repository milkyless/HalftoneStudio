"""PyGIMP 無頭測試。

以 python-fu-eval 透過 runpy 載入（runpy 是表達式，可在 eval 中使用）：
    (python-fu-eval RUN-NONINTERACTIVE
        "runpy.run_path('C:/Users/Milky/Desktop/Z/test/run_test.py')")
"""
import os

from gimpfu import gimp, pdb

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 400, 300


def log(msg):
    print("[FH] %s" % msg)


def save(img, path):
    """嘗試多種存檔方式。"""
    for attempt in (
        lambda: pdb.gimp_file_save(img, path, path),
        lambda: pdb.gimp_file_save(0, img, path, path),
        lambda: pdb.gimp_file_save(img, path),
    ):
        try:
            attempt()
            if os.path.exists(path):
                return True
        except Exception:
            continue
    return False


def make_gradient():
    img = gimp.Image.new(W, H, gimp.RGB)
    layer = gimp.Layer.new(img, W, H, gimp.RGB_IMAGE, "bg", 100,
                           gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)

    for x in range(0, W, 1):
        v = int(round(255.0 * x / (W - 1)))
        for y in range(0, H, 4):
            pdb.gimp_drawable_set_pixel(layer, x, y, (v, v, v))

    return img, layer


def mean_gray(layer):
    total, count = 0.0, 0
    for x in range(0, W, 2):
        for y in range(0, H, 4):
            px = pdb.gimp_drawable_get_pixel(layer, x, y)
            total += sum(px[1][0:3]) / 3.0
            count += 1
    return total / max(count, 1) / 255.0


def run_case(tag, stoch, shape, mode):
    img, layer = make_gradient()
    before = mean_gray(layer)

    try:
        pdb.gimp_film_halftone(layer,
                               300.0, 40.0, 0, shape, stoch, 1.0, 64, 15.0,
                               0.15, 0.03, 0.95, mode, 1, 0)
    except Exception as exc:
        log("%-9s FILTER FAILED: %s" % (tag, exc))
        pdb.gimp_image_delete(img)
        return

    after = mean_gray(layer)
    path = os.path.join(HERE, "out_%s.png" % tag)
    saved = save(img, path)
    log("%-9s gray %.4f -> %.4f | ink %.4f | saved=%s"
        % (tag, before, after, 1.0 - after, saved))
    pdb.gimp_image_delete(img)


def main():
    log("BEGIN")
    run_case("stoch00", 0.0, 0.0, 0)
    run_case("stoch50", 0.5, 0.0, 0)
    run_case("stoch100", 1.0, 0.0, 0)
    run_case("organic", 0.2, 0.6, 0)
    run_case("binary", 0.0, 0.0, 1)
    log("END")


main()
