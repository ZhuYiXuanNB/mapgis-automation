# -*- coding: utf-8 -*-
"""把已有 .WT 的点符号（子图号）改成指定值，其余字节不动。
用法：python scripts/set_symbol.py output_strahler\采样点位_分级.WT --symbol 48 --size 2.0
"""
import sys, os, struct, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapgis_wl import read_wt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wt")
    ap.add_argument("--symbol", type=int, default=48)
    ap.add_argument("--size", type=float, default=None, help="子图高/宽 mm（不给则不改）")
    ap.add_argument("--color", type=int, default=None, help="颜色号（不给则不改）")
    a = ap.parse_args()

    b = bytearray(open(a.wt, "rb").read())
    assert bytes(b[:8]) == b"WMAP`D22", "不是点文件（魔数不是 WMAP`D22）"
    ds = struct.unpack_from("<i", b, 12)[0]
    cstart, cvol = struct.unpack_from("<2i", b, ds)
    n = cvol // 93 - 1
    old = set()
    for i in range(1, n + 1):
        off = cstart + i * 93
        old.add(struct.unpack_from("<h", b, off + 33)[0])
        struct.pack_into("<h", b, off + 33, a.symbol)
        if a.size is not None:
            struct.pack_into("<f", b, off + 37, a.size)
            struct.pack_into("<f", b, off + 41, a.size)
        if a.color is not None:
            b[off + 75] = a.color
    open(a.wt, "wb").write(b)
    print("%s: %d 个点, 子图号 %s -> %d%s" % (
        a.wt, n, sorted(old), a.symbol,
        "" if a.size is None else ", 高宽 %.2f mm" % a.size))
    pts, _ = read_wt(a.wt)
    print("  回读校验: %d 点, 首个点符号=%d" % (len(pts), pts[0][3]))


if __name__ == "__main__":
    main()
