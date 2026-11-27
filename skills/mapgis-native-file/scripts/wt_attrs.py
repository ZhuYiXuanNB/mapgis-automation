# -*- coding: utf-8 -*-
r"""
查看 / 修改 .WT 属性表（就地改字节，不动几何）
==============================================

    # 导出属性到 CSV
    python scripts/wt_attrs.py dump --wt 控制点.WT --out attrs.csv

    # 按「点号」定位，改一个字段
    python scripts/wt_attrs.py set --wt 副本.WT --where 点号=001C1 --set 类型=复核点

    # 按条件批量改
    python scripts/wt_attrs.py set --wt 副本.WT --where 类型=必采 --set 单元=A

设计：只重写属性记录区里那几个字节，段指针、坐标、注记一概不碰。
所以这一步比「读出来重新生成」安全 —— 不会因为字段布局差异把文件写坏。
"""
import sys, os, struct, argparse, csv
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapgis_native import Skeleton, _read_fields

TYP_NAME = {0: "str", 1: "byte", 2: "short", 3: "int", 4: "float", 5: "double"}


def _open(path):
    raw = bytearray(open(path, "rb").read())
    sk = Skeleton(bytes(raw), os.path.basename(path))
    if sk.kind != "WT":
        raise SystemExit("%s 不是点/注记文件（魔数 %s）" % (path, sk.kind))
    attr_off = sk.entry(2)[0]
    fields, rc, rl, r0 = _read_fields(bytes(raw), attr_off)
    if not fields:
        raise SystemExit("%s 没有属性表，先挂字段再来" % path)
    return raw, fields, rc, rl, r0


def _get(buf, typ, off, wid):
    if typ == 0:
        return buf[off:off + wid].split(b"\x00")[0].decode("gbk", "replace")
    if typ == 1:
        return struct.unpack_from("<b", buf, off)[0]
    if typ == 2:
        return struct.unpack_from("<h", buf, off)[0]
    if typ == 3:
        return struct.unpack_from("<i", buf, off)[0]
    if typ == 4:
        return struct.unpack_from("<f", buf, off)[0]
    if typ == 5:
        return struct.unpack_from("<d", buf, off)[0]
    return None


def dump(a):
    raw, fields, rc, rl, r0 = _open(a.wt)
    names = [f[0] for f in fields]
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(names)
        for i in range(1, rc):                      # 跳过首条空记录
            rec = r0 + i * rl
            w.writerow([_get(raw, t, rec + off, wid) for (_n, t, off, wid) in fields])
    print("已导出 %d 条记录 × %d 字段 -> %s" % (rc - 1, len(names), a.out))


def set_attr(a):
    cond_f, cond_v = a.where.split("=", 1)
    set_f, set_v = a.set.split("=", 1)
    raw, fields, rc, rl, r0 = _open(a.wt)
    d = {f[0]: f for f in fields}
    for name in (cond_f, set_f):
        if name not in d:
            raise SystemExit("字段 %r 不存在；可用: %s" % (name, list(d)))
    _c, c_typ, c_off, c_wid = d[cond_f]
    _s, s_typ, s_off, s_wid = d[set_f]
    hit = 0
    for i in range(1, rc):
        rec = r0 + i * rl
        if str(_get(raw, c_typ, rec + c_off, c_wid)) != cond_v:
            continue
        pos = rec + s_off
        if s_typ == 0:
            b = set_v.encode("gbk")
            if len(b) > s_wid - 1:
                raise SystemExit("值太长：%d 字节 > 字段容量 %d" % (len(b), s_wid - 1))
            raw[pos:pos + s_wid] = b + bytes(s_wid - len(b))
        elif s_typ == 1:
            struct.pack_into("<b", raw, pos, int(set_v))
        elif s_typ == 2:
            struct.pack_into("<h", raw, pos, int(set_v))
        elif s_typ == 3:
            struct.pack_into("<i", raw, pos, int(set_v))
        elif s_typ == 4:
            struct.pack_into("<f", raw, pos, float(set_v))
        elif s_typ == 5:
            struct.pack_into("<d", raw, pos, float(set_v))
        else:
            raise SystemExit("不支持的字段类型 %d" % s_typ)
        hit += 1
    if hit == 0:
        raise SystemExit("没有匹配 %s=%s 的记录" % (cond_f, cond_v))
    open(a.wt, "wb").write(raw)
    print("已改 %s=%s 的 %s -> %s（%d 条记录）" % (cond_f, cond_v, set_f, set_v, hit))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="属性导出 CSV"); d.add_argument("--wt", required=True)
    d.add_argument("--out", default="attrs.csv")
    s = sub.add_parser("set", help="按条件就地改值"); s.add_argument("--wt", required=True)
    s.add_argument("--where", required=True, help="字段=值")
    s.add_argument("--set", required=True, help="字段=新值")
    a = ap.parse_args()
    dump(a) if a.cmd == "dump" else set_attr(a)


if __name__ == "__main__":
    main()