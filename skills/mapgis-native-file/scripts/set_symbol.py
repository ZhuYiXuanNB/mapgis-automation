# -*- coding: utf-8 -*-
"""把已有 .WT 的子图号 / 子图高宽 / 颜色改成指定值，其余字节一律不动。

    python scripts/set_symbol.py 控制点.WT --symbol 48 --size 2.0

为什么不重新生成：属性表、注记、图层顺序都在文件里，重新生成会丢；
这里只打 3 个字节，风险最小。
"""
import sys, os, struct, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapgis_native import Skeleton, POINT_REC, read


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wt")
    ap.add_argument("--symbol", type=int, default=None, help="子图号（不给则不改）")
    ap.add_argument("--size", type=float, default=None, help="子图高/宽 mm（不给则不改）")
    ap.add_argument("--color", type=int, default=None, help="颜色号（不给则不改）")
    a = ap.parse_args()
    if a.symbol is None and a.size is None and a.color is None:
        raise SystemExit("至少给一个 --symbol / --size / --color")

    raw = bytearray(open(a.wt, "rb").read())
    sk = Skeleton(bytes(raw), os.path.basename(a.wt))
    if sk.kind != "WT":
        raise SystemExit("%s 不是点/注记文件（魔数 %s）" % (a.wt, sk.kind))
    if sk.entry(1)[1] > 2:
        raise SystemExit("这是注记文件（有文本池），+33 是字高不是子图号；"
                         "要改字号请用 write_labels(height=...) 重新生成")

    cstart, cvol = sk.entry(0)
    n = cvol // POINT_REC - 1
    if n <= 0:
        raise SystemExit("文件里没有点（%d）" % n)
    old = set()
    for i in range(1, n + 1):
        off = cstart + i * POINT_REC
        old.add(struct.unpack_from("<h", raw, off + 33)[0])
        if a.symbol is not None:
            struct.pack_into("<h", raw, off + 33, a.symbol)
        if a.size is not None:
            struct.pack_into("<f", raw, off + 37, a.size)
            struct.pack_into("<f", raw, off + 41, a.size)
        if a.color is not None:
            raw[off + 75] = a.color & 0xFF
    open(a.wt, "wb").write(raw)

    print("%s: %d 个点，子图号 %s -> %s%s%s" % (
        a.wt, n, sorted(old),
        "-" if a.symbol is None else a.symbol,
        "" if a.size is None else ", 高宽 %.2f mm" % a.size,
        "" if a.color is None else ", 颜色 %d" % a.color))
    d = read(a.wt)
    print("  回读校验: %d 点, 首点 X=%.3f Y=%.3f" % (d["count"], d["records"][0]["X"], d["records"][0]["Y"]))


if __name__ == "__main__":
    main()