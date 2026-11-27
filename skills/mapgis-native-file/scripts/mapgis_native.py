# -*- coding: utf-8 -*-
r"""
mapgis_native —— MAPGIS 6.7 点(.WT)/线(.WL) 原生文件读写，纯标准库。

核心原则（血泪换来的）：
    不推算结构，克隆骨架，只重建数据段，回填表头。

用法：
    from mapgis_native import Skeleton, write_labels, verify

    sk = Skeleton.from_file(r"D:\...\图框.WT")      # 任一本机能打开的注记文件
    items = [dict(x=10510, y=57150, text="A#-1", attr="001A1", vis=2)]
    write_labels(r"点号.WT", sk, items, height=1.2, width=1.0, layer=12)
    print(verify(r"点号.WT"))
"""

import struct, os, sys, json

__all__ = ["Skeleton", "write_points", "write_lines", "write_labels",
           "read", "verify", "subscript", "FIELDS"]

IDX_N    = 16          # 索引表固定 16 项
IDX_SZ   = 10          # 每项：int32 start + int32 size + u16 0xffff
MAGIC    = {b"WMAP`D21": "WL", b"WMAP`D22": "WT", b"WMAP`D23": "WP"}

HDR_COUNT = 260        # u16 图元数
HDR_REC   = 264        # u16 记录数（含首条空记录）
HDR_EXT   = 304        # 4 x double xmin/ymin/xmax/ymax
IDX_PTR   = 12         # int32 索引区起点（通常 657）

POINT_REC = 93
LINE_REC  = 57
ATTR_HEAD = 322
ATTR_GAP  = 18
FIELD_DESC= 39
POOL_PREFIX = 1602     # 注记文本池前缀（样式区）

FIELDS = {"str": 0, "int": 3, "double": 5}


class Skeleton:
    """从 MAPGIS 自己写出的文件里取骨架。"""

    def __init__(self, raw, name=""):
        if len(raw) < 700:
            raise ValueError("文件太小，不像 MAPGIS 文件: %s (%d B)" % (name, len(raw)))
        self.raw  = raw
        self.name = name
        self.kind = MAGIC.get(raw[:8], "?")
        idx = struct.unpack_from("<i", raw, IDX_PTR)[0]
        self.idx = idx if 0 < idx < len(raw) - 160 else 657
        self.data_off = self.idx + IDX_N * IDX_SZ

    @classmethod
    def from_file(cls, path):
        with open(path, "rb") as f:
            return cls(f.read(), os.path.basename(path))

    @property
    def header(self):
        return self.raw[:self.idx]

    def entry(self, k):
        return struct.unpack_from("<2i", self.raw, self.idx + k * IDX_SZ)

    def seg(self, k):
        s, n = self.entry(k)
        return self.raw[s:s + n]

    def point_template(self):
        s, _ = self.entry(0)
        return self.raw[s + POINT_REC: s + 2 * POINT_REC]

    def line_template(self):
        s, _ = self.entry(0)
        return self.raw[s + LINE_REC: s + 2 * LINE_REC]

    def pool_prefix(self, size=POOL_PREFIX):
        s, _ = self.entry(1)
        return self.raw[s:s + size]

    def attr_prefix(self):
        s, _ = self.entry(2)
        return self.raw[s:s + ATTR_HEAD]

    def flag_prefix(self):
        s, _ = self.entry(4)
        return self.raw[s:s + 4]

    def attrs_desc(self):
        s, _ = self.entry(2)
        return self.raw[s + 348: s + 348 + FIELD_DESC]

    def tail_blocks(self):
        """WL 的附加表 A/B（索引 4、5），整块搬运。"""
        return self.seg(4), self.seg(5)


def _assemble(path, sk, segs, count, extent):
    """segs: [(data, declared_size|None)]；declared 与 len 不同，用于复刻原文件的重叠写法。"""
    header = bytearray(sk.header)
    struct.pack_into("<H", header, HDR_COUNT, count)
    struct.pack_into("<H", header, HDR_REC, count + 1)
    struct.pack_into("<4d", header, HDR_EXT, *extent)

    starts, cur = [], sk.data_off
    for data, _decl in segs:
        starts.append(cur)
        cur += len(data)
    total = cur

    buf = bytearray(total)
    buf[:len(header)] = header
    for k in range(IDX_N):
        if k < len(segs):
            data, decl = segs[k]
            struct.pack_into("<2iH", buf, sk.idx + k * IDX_SZ,
                             starts[k], len(data) if decl is None else decl, 0xFFFF)
        else:
            struct.pack_into("<2iH", buf, sk.idx + k * IDX_SZ, 0, 0, 0xFFFF)
    for k, (data, _decl) in enumerate(segs):
        buf[starts[k]:starts[k] + len(data)] = data
    with open(path, "wb") as f:
        f.write(buf)
    return dict(file=os.path.basename(path), count=count, size=total)


def _field_layout(fields):
    offs, o = [], 1
    for (_n, _t, w, _dw, _f) in fields:
        offs.append(o)
        o += w
    rl = o
    desc = b"".join(
        struct.pack("<20sBihhih4x", nm.encode("gbk"), tp, ofs, w, dw, fl, i)
        for i, ((nm, tp, w, dw, fl), ofs) in enumerate(zip(fields, offs)))
    return rl, desc, offs


def _extent(xs, ys, pad):
    return (min(xs) - pad[0], min(ys) - pad[1], max(xs) + pad[2], max(ys) + pad[3])


def write_points(path, sk, recs, fields, symbol=48, color=134, layer=0,
                 height=1.5, width=1.5, half=1.5, x_key="X", y_key="Y",
                 attr_sk=None, extent_pad=(2, 2, 2, 2)):
    """写点文件（可带属性表）。recs: [dict(字段名=值, X=, Y=)]；fields: [(名, 类型, 宽, 小数位, 标志)]"""
    n = len(recs)
    rl, desc, offs = _field_layout(fields)

    attr_recs = bytearray(rl)
    for r in recs:
        rec = bytearray(rl)
        rec[0] = 1
        for (nm, tp, w, _dw, _fl), ofs in zip(fields, offs):
            v = r.get(nm)
            if tp == 0:
                s = ("" if v is None else str(v)).encode("gbk")[:w - 1]
                rec[ofs:ofs + len(s)] = s
            elif tp == 3:
                struct.pack_into("<i", rec, ofs, int(v or 0))
            elif tp == 5:
                struct.pack_into("<d", rec, ofs, float(v or 0))
        attr_recs += rec

    coords = bytearray(POINT_REC * (n + 1))
    tpl = sk.point_template()
    for i, r in enumerate(recs):
        o = (i + 1) * POINT_REC
        coords[o:o + POINT_REC] = tpl
        coords[o] = 1
        coords[o + 31] = 1
        struct.pack_into("<h", coords, o + 33, symbol)   # i16：≤255 与 u8 字节等价，>255 仍可写
        struct.pack_into("<2d", coords, o + 7, r[x_key], r[y_key])
        struct.pack_into("<f", coords, o + 37, height)
        struct.pack_into("<f", coords, o + 41, width)
        coords[o + 75] = color
        coords[o + 83] = layer

    attr = bytearray(ATTR_HEAD + 8 + ATTR_GAP + FIELD_DESC * len(fields) + len(attr_recs))
    attr[:ATTR_HEAD] = (attr_sk or sk).attr_prefix()
    struct.pack_into("<hIh", attr, ATTR_HEAD, len(fields), n + 1, rl)
    attr[348:348 + FIELD_DESC * len(fields)] = desc
    attr[348 + FIELD_DESC * len(fields):] = attr_recs

    bbox = bytearray(32 * (n + 1))
    for i, r in enumerate(recs):
        struct.pack_into("<4d", bbox, (i + 1) * 32,
                         r[x_key] - half, r[y_key] - half,
                         r[x_key] + half, r[y_key] + half)

    flag = bytearray(4 + 4 * n)
    flag[:4] = sk.flag_prefix()
    for i in range(n):
        struct.pack_into("<i", flag, 4 + 4 * i, 65536)

    xs = [r[x_key] for r in recs]; ys = [r[y_key] for r in recs]
    return _assemble(path, sk,
                     [(bytes(coords), None), (b"\x00\x00", None), (bytes(attr), None),
                      (bytes(bbox), None), (bytes(flag), None)],
                     n, _extent(xs, ys, extent_pad))


def write_labels(path, sk, items, height=1.2, width=1.0, gap=0.05, color=1, layer=12,
                 field="点号", field_width=13, attr_sk=None, extent_pad=(2, 2, 8, 2)):
    """写注记文件。items: [dict(x=, y=, text=, attr=, vis=可见字数)]"""
    n = len(items)
    texts = [it["text"].encode("gbk") for it in items]
    pool_vol = POOL_PREFIX + sum(len(t) for t in texts)
    pool = bytearray(pool_vol)
    pool[:POOL_PREFIX] = sk.pool_prefix()
    cur = POOL_PREFIX
    for t in texts:
        pool[cur:cur + len(t)] = t
        cur += len(t)

    rl = 1 + field_width
    attr = bytearray(ATTR_HEAD + 8 + ATTR_GAP + FIELD_DESC + (n + 1) * rl)
    attr[:ATTR_HEAD] = (attr_sk or sk).attr_prefix()
    struct.pack_into("<hIh", attr, ATTR_HEAD, 1, n + 1, rl)
    struct.pack_into("<20sBihhih4x", attr, 348, field.encode("gbk"), 0, 1,
                     field_width, field_width - 1, 256, 0)
    r0 = 348 + FIELD_DESC
    for i, it in enumerate(items):
        q = r0 + (i + 1) * rl
        attr[q] = 1
        s = str(it["attr"]).encode("gbk")[:field_width - 1]
        attr[q + 1:q + 1 + len(s)] = s

    coords = bytearray(POINT_REC * (n + 1))
    tpl = sk.point_template()
    cur = POOL_PREFIX
    for i, it in enumerate(items):
        o = (i + 1) * POINT_REC
        coords[o:o + POINT_REC] = tpl
        coords[o] = 1
        struct.pack_into("<H", coords, o + 1, len(texts[i]))
        struct.pack_into("<I", coords, o + 3, cur)
        struct.pack_into("<2d", coords, o + 7, it["x"], it["y"])
        coords[o + 31] = 0
        struct.pack_into("<f", coords, o + 33, it.get("height", height))
        struct.pack_into("<f", coords, o + 37, it.get("width", width))
        struct.pack_into("<f", coords, o + 41, gap)
        struct.pack_into("<f", coords, o + 45, it.get("angle", 0.0))
        coords[o + 75] = color
        coords[o + 83] = layer
        cur += len(texts[i])

    bbox = bytearray(32 * (n + 1))
    for i, it in enumerate(items):
        h = it.get("height", height); w = it.get("width", width)
        vis = it.get("vis", len(it["text"]))
        struct.pack_into("<4d", bbox, (i + 1) * 32,
                         it["x"], it["y"] - 0.35 * h,
                         it["x"] + vis * w * 1.05, it["y"] + 0.95 * h)

    flag = bytearray(4 + 4 * n)
    flag[:4] = sk.flag_prefix()
    for i in range(n):
        struct.pack_into("<i", flag, 4 + 4 * i, 65536)

    xs = [it["x"] for it in items]; ys = [it["y"] for it in items]
    return _assemble(path, sk,
                     [(bytes(coords), None), (bytes(pool), None), (bytes(attr), None),
                      (bytes(bbox), None), (bytes(flag), None)],
                     n, _extent(xs, ys, extent_pad))


def write_lines(path, sk, segments, attr_sk=None, extent_pad=(2, 2, 2, 2)):
    """写线文件。segments: [(pts, (线型号, 颜色, 线宽)), ...]"""
    m = len(segments)
    lines = bytearray(LINE_REC * (m + 1))
    coords = bytearray(2)
    for i, (pts, (ty, col, wid)) in enumerate(segments):
        o = (i + 1) * LINE_REC
        lines[o] = 1
        lines[o + 1] = 2
        struct.pack_into("<i", lines, o + 10, len(pts))
        struct.pack_into("<i", lines, o + 14, len(coords))
        struct.pack_into("<i", lines, o + 22, ty)
        struct.pack_into("<i", lines, o + 26, col)
        struct.pack_into("<f", lines, o + 30, wid)
        struct.pack_into("<f", lines, o + 34, 10.0)
        struct.pack_into("<f", lines, o + 38, 10.0)
        struct.pack_into("<i", lines, o + 42, 1)
        struct.pack_into("<i", lines, o + 46, 20)
        for (x, y) in pts:
            coords += struct.pack("<2d", x, y)

    attr = bytearray(348 + FIELD_DESC + (m + 1) * 5)
    _as = attr_sk or sk
    attr[:ATTR_HEAD] = _as.attr_prefix()
    struct.pack_into("<hIh", attr, ATTR_HEAD, 1, m + 1, 5)
    attr[348:348 + FIELD_DESC] = _as.attrs_desc()
    r0 = 348 + FIELD_DESC
    for i in range(m):
        q = r0 + (i + 1) * 5
        attr[q] = 1
        struct.pack_into("<i", attr, q + 1, i + 1)

    blk24 = bytearray(24 * (m + 1))
    blk_a, blk_b = sk.tail_blocks()
    bbox = bytearray(32 * (m + 1))
    for i, (pts, _s) in enumerate(segments):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        struct.pack_into("<4d", bbox, (i + 1) * 32, min(xs), min(ys), max(xs), max(ys))
    flag = bytearray(4 + 4 * m)
    for i in range(m):
        struct.pack_into("<i", flag, 4 + 4 * i, 65536)

    allx = [p[0] for pts, _s in segments for p in pts]
    ally = [p[1] for pts, _s in segments for p in pts]
    return _assemble(path, sk,
                     [(bytes(lines), None), (bytes(coords), None), (bytes(attr), None),
                      (bytes(blk24), None), (blk_a, None), (blk_b, None),
                      (bytes(bbox), None), (bytes(flag), None)],
                     m, _extent(allx, ally, extent_pad))


def _read_fields(raw, attr_off):
    fc = struct.unpack_from("<h", raw, attr_off + 322)[0]
    rc = struct.unpack_from("<i", raw, attr_off + 324)[0]
    rl = struct.unpack_from("<h", raw, attr_off + 328)[0]
    fields = []
    for i in range(fc):
        d = attr_off + 348 + i * FIELD_DESC
        name = raw[d:d + 20].split(b"\x00")[0].decode("gbk", "replace")
        typ = raw[d + 20]
        off = struct.unpack_from("<i", raw, d + 21)[0]
        wid = struct.unpack_from("<h", raw, d + 25)[0]
        fields.append((name, typ, off, wid))
    return fields, rc, rl, attr_off + 348 + fc * FIELD_DESC


def read(path):
    """返回 dict(kind, count, records=[{X,Y,文本/属性}])"""
    with open(path, "rb") as f:
        raw = f.read()
    sk = Skeleton(raw, os.path.basename(path))
    out = dict(file=os.path.basename(path), kind=sk.kind, size=len(raw))
    if sk.kind == "WT":
        cs, cn = sk.entry(0)
        n = cn // POINT_REC - 1
        ps, pn = sk.entry(1)
        is_label = pn > 2
        attr_off = sk.entry(2)[0]
        fields, _rc, rl, r0 = _read_fields(raw, attr_off)
        recs = []
        for i in range(1, n + 1):
            o = cs + i * POINT_REC
            x, y = struct.unpack_from("<2d", raw, o + 7)
            r = dict(X=x, Y=y, color=raw[o + 75], layer=raw[o + 83])
            if not is_label:
                r["symbol"] = struct.unpack_from("<h", raw, o + 33)[0]
            if is_label:
                tl = struct.unpack_from("<H", raw, o + 1)[0]
                to = struct.unpack_from("<I", raw, o + 3)[0]
                r["text"] = raw[ps + to: ps + to + tl].decode("gbk", "replace")
                r["height"] = struct.unpack_from("<f", raw, o + 33)[0]
                r["width"] = struct.unpack_from("<f", raw, o + 37)[0]
            for (nm, typ, off, wid) in fields:
                q = r0 + i * rl + off
                if typ == 0:
                    r[nm] = raw[q:q + wid].split(b"\x00")[0].decode("gbk", "replace")
                elif typ == 3:
                    r[nm] = struct.unpack_from("<i", raw, q)[0]
                elif typ == 5:
                    r[nm] = struct.unpack_from("<d", raw, q)[0]
            recs.append(r)
        out.update(count=n, is_label=is_label, fields=[f[0] for f in fields], records=recs)
    elif sk.kind == "WL":
        ls, ln = sk.entry(0)
        m = ln // LINE_REC - 1
        cs, _ = sk.entry(1)
        recs = []
        for i in range(1, m + 1):
            o = ls + i * LINE_REC
            npts = struct.unpack_from("<i", raw, o + 10)[0]
            off = struct.unpack_from("<i", raw, o + 14)[0]
            recs.append(dict(
                n=npts,
                linetype=struct.unpack_from("<i", raw, o + 22)[0],
                color=struct.unpack_from("<i", raw, o + 26)[0],
                width=struct.unpack_from("<f", raw, o + 30)[0],
                pts=[struct.unpack_from("<2d", raw, cs + off + k * 16) for k in range(npts)]))
        out.update(count=m, records=recs)
    return out


def verify(path):
    """结构自检：表头计数、索引首尾相接、末段收尾 = 文件长度。"""
    with open(path, "rb") as f:
        raw = f.read()
    sk = Skeleton(raw, os.path.basename(path))
    cnt = struct.unpack_from("<H", raw, HDR_COUNT)[0]
    rec = struct.unpack_from("<H", raw, HDR_REC)[0]
    used = [(s, n) for (s, n) in (sk.entry(k) for k in range(IDX_N)) if n]
    chain_ok, prev_end = True, None
    for s, n in used:
        if prev_end is not None and s != prev_end:
            chain_ok = False
        prev_end = s + n
    tail_ok = (prev_end == len(raw)) if used else False
    unit = POINT_REC if sk.kind == "WT" else LINE_REC
    n_units = used[0][1] // unit - 1 if used else 0
    report = dict(file=os.path.basename(path), kind=sk.kind, bytes=len(raw),
                  header_count=cnt, header_records=rec,
                  count_match=(cnt == n_units and rec == cnt + 1),
                  units=n_units, chain_ok=chain_ok, tail_ok=tail_ok)
    report["ok"] = all([report["count_match"], chain_ok, tail_ok])
    return report


def subscript(s):
    """点号转下标写法：001A1 -> 001A#-1（MapGis 把 #- 后的字符排成下标）。"""
    i = len(s)
    while i > 0 and s[i - 1].isdigit():
        i -= 1
    return s[:i] + "#-" + s[i:] if i < len(s) else s


def _main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "verify":
        bad = 0
        for p in rest:
            r = verify(p)
            print(("OK   " if r["ok"] else "FAIL ") + json.dumps(r, ensure_ascii=False))
            bad += 0 if r["ok"] else 1
        return 1 if bad else 0
    if cmd == "inspect":
        for p in rest:
            d = read(p)
            print(json.dumps({k: v for k, v in d.items() if k != "records"}, ensure_ascii=False))
            for r in d["records"][:3]:
                print("  ", json.dumps(r, ensure_ascii=False)[:300])
        return 0
    if cmd == "labels":
        import argparse
        ap = argparse.ArgumentParser(prog="labels")
        ap.add_argument("--template", required=True, help="任一本机能打开的注记 .WT")
        ap.add_argument("--from", dest="src", required=True, help="点文件 .WT（读属性）")
        ap.add_argument("--out", required=True)
        ap.add_argument("--field", default="点号")
        ap.add_argument("--height", type=float, default=1.2)
        ap.add_argument("--width", type=float, default=1.0)
        ap.add_argument("--layer", type=int, default=12)
        ap.add_argument("--color", type=int, default=1)
        a = ap.parse_args(rest)
        sk = Skeleton.from_file(a.template)
        src = read(a.src)
        items = []
        for r in src["records"]:
            t = str(r.get(a.field, ""))
            if not t:
                continue
            items.append(dict(x=r["X"] + 0.7, y=r["Y"] - 0.35, text=subscript(t),
                              attr=t, vis=len(subscript(t).replace("#-", ""))))
        print(write_labels(a.out, sk, items, height=a.height, width=a.width,
                           layer=a.layer, color=a.color))
        return 0
    print("未知命令：%s" % cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
