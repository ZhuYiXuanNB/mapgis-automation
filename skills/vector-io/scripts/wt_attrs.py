# -*- coding: utf-8 -*-
r"""
查看 / 修改 .WT 属性表
=====================
# 导出属性到 CSV
python scripts\wt_attrs.py dump --wt output_strahler\采样点位_分级.WT --out attrs.csv

# 就地修改某条记录的某个字段（按 点号 定位）
python scripts\wt_attrs.py set --wt 副本.WT --where 点号=001C1 --set 类型=复核点

# 批量：按条件改（如把所有 Strahler=1 的类型改成“一级水系下游”）
python scripts\wt_attrs.py set --wt 副本.WT --where Strahler=1 --set 类型=一级水系下游
"""
import sys, os, struct, argparse, csv
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapgis_wl import _index, read_wt_attrs

TYP = {"byte": 1, "short": 2, "int": 3, "float": 4, "double": 5, "str": 0}


def dump(a):
    fields, rows = read_wt_attrs(a.wt)
    names = [f[0] for f in fields]
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(names)
        for r in rows[1:]:                       # 跳过首条空记录
            w.writerow([r[n] for n in names])
    print("已导出 %d 条记录 × %d 字段 -> %s" % (len(rows) - 1, len(names), a.out))


def set_attr(a):
    cond_f, cond_v = a.where.split("=", 1)
    set_f, set_v = a.set.split("=", 1)
    b = bytearray(open(a.wt, "rb").read())
    idx, _ = _index(b)
    start = idx[2][0]
    nf = struct.unpack_from("<h", b, start + 322)[0]
    nr = struct.unpack_from("<i", b, start + 324)[0]
    rl = struct.unpack_from("<h", b, start + 328)[0]
    fields = {}
    for k in range(nf):
        o = start + 348 + 39 * k
        name = b[o:o + 20].split(b"\x00")[0].decode("gbk", "ignore")
        fields[name] = (b[o + 20], struct.unpack_from("<i", b, o + 21)[0],
                        struct.unpack_from("<h", b, o + 25)[0])
    if cond_f not in fields or set_f not in fields:
        raise SystemExit("字段不存在；可用: %s" % list(fields))
    base = start + 348 + 39 * nf
    hit = 0
    for i in range(nr):
        off = base + i * rl
        rec = b[off:off + rl]
        t, pos, w = fields[cond_f]
        if t == 0:
            val = rec[pos:pos + w].split(b"\x00")[0].decode("gbk", "ignore")
        elif t == 3:
            val = str(struct.unpack_from("<i", rec, pos)[0])
        elif t == 5:
            val = str(struct.unpack_from("<d", rec, pos)[0])
        else:
            val = str(rec[pos])
        if val != cond_v:
            continue
        t2, pos2, w2 = fields[set_f]
        if t2 == 0:
            s = set_v.encode("gbk")
            if len(s) > w2 - 1:
                raise SystemExit("值太长：%d 字节 > 字段容量 %d" % (len(s), w2 - 1))
            b[off + pos2:off + pos2 + w2] = s + bytes(w2 - len(s))
        elif t2 == 3:
            struct.pack_into("<i", b, off + pos2, int(set_v))
        elif t2 == 5:
            struct.pack_into("<d", b, off + pos2, float(set_v))
        else:
            b[off + pos2] = int(set_v)
        hit += 1
    if hit == 0:
        raise SystemExit("没有匹配的记录")
    open(a.wt, "wb").write(b)
    print("已修改 %s 的 %s = %s（%d 条记录）" % (a.where, set_f, set_v, hit))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump"); d.add_argument("--wt", required=True); d.add_argument("--out", default="attrs.csv")
    s = sub.add_parser("set")
    s.add_argument("--wt", required=True)
    s.add_argument("--where", required=True, help="字段=值")
    s.add_argument("--set", required=True, help="字段=新值")
    a = ap.parse_args()
    if a.cmd == "dump":
        dump(a)
    else:
        set_attr(a)


if __name__ == "__main__":
    main()
