# -*- coding: utf-8 -*-
"""
MAPGIS 6.7 矢量文件读写：.WT 点 / .WL 线 / .WP 面 + 属性表 + 注记点
=====================================================================
纯 Python 二进制读写，不依赖 MAPGIS 桌面。

结构依据（本机字节级实测；细节见 reference/format.md 与仓库 docs/binary-format.md）：
  [657B 文件头][16 项 × 10B 索引区][数据体]
  索引项 = <int32 start><int32 volume><2B 0xFFFF>
  .WL: idx0 线索引(57B/条,首条空) idx1 坐标(2B 前导 + 16B/坐标对) idx2 属性
       idx3 结点表(24B) idx4 55B idx5 元数据(392B) idx6 框表(32B) idx7 标志(4+4n)
  .WT: idx0 点记录(93B/条,首条空) idx1 文本池(1602B 前缀 + 拼接 GBK) idx2 属性
       idx3 标注框((n+1)*32B) idx4 标志(4B + 4B*n)
  .WP: idx0 弧索引 idx1 坐标 idx2 元数据 idx3 拓扑(24B) idx8 区参数(40B) idx9 属性
       idx10 区标注框 idx12 文件脚

坐标单位：图面毫米（1:50000 时 1 mm = 50 m）；经纬度文件则另论。

主要 API
--------
read_wl(path) -> [{'id','xy','ltype','color','layer'}]
write_wl(path, polylines, ltype, color, width, layer, template=...)
read_wt(path) -> [(x, y, kind, symbol)]
write_wt(path, points, fields=..., rows=..., template=..., symbol=48, size=2.0)
read_wt_attrs(path) -> (fields, rows)
write_wt_annot(path, items, template=...)     # 注记点（文字）
read_wt_annot(path) -> [(x, y, text, h, w, gap, angle, color, layer)]
"""
import struct, os
import numpy as np

DATA_START = 657
W_MAGIC = b"WMAP`D21"     # 线
T_MAGIC = b"WMAP`D22"     # 点
P_MAGIC = b"WMAP`D23"     # 区


def _index(b):
    ds = struct.unpack_from("<i", b, 12)[0]
    return [(struct.unpack_from("<2i", b, ds + 10 * i)) for i in range(16)], ds


def read_header(b):
    g = lambda o, f: struct.unpack_from(f, b, o)[0]
    return dict(magic=b[:8], fileid=g(8, "<i"), data_start=g(12, "<i"),
                proj=b[109], ellip=b[110], scale=g(143, "<d"),
                counts=struct.unpack_from("<6I", b, 260),
                bbox=struct.unpack_from("<4d", b, 304), flag=b[336])


# --------------------------------------------------------------- WL reader
def read_wl(path):
    """返回 [{'id','xy','ltype','color','layer'}, ...]，xy 为 (N,2) float64"""
    b = open(path, "rb").read()
    idx, ds = _index(b)
    (lstart, lvol), (cstart, _) = idx[0], idx[1]
    n = lvol // 57 - 1
    out = []
    for i in range(1, n + 1):
        off = lstart + i * 57
        nnode, coff = struct.unpack_from("<2i", b, off + 10)
        if nnode <= 0:
            continue
        xy = np.frombuffer(b, dtype="<f8", count=2 * nnode,
                           offset=cstart + coff).reshape(-1, 2).copy()
        out.append(dict(id=i, xy=xy,
                        ltype=struct.unpack_from("<h", b, off + 22)[0],
                        color=struct.unpack_from("<h", b, off + 26)[0],
                        layer=b[off + 47]))
    return out


# --------------------------------------------------------------- WT writer
_FIELD_TYPES = {"str": 0, "byte": 1, "short": 2, "int": 3, "float": 4, "double": 5}
_TPY_WIDTH = {"byte": 1, "short": 2, "int": 4, "float": 4, "double": 8}


def _attr_section(fields, rows, prefix_template=None):
    """fields: [(name, kind, width)]  rows: list of tuples"""
    fdesc = b""
    pos = 1
    layout = []
    for name, kind, width in fields:
        t = _FIELD_TYPES[kind]
        nb = name.encode("gbk")
        decl = width if kind == "str" else _TPY_WIDTH[kind]
        w2 = decl if kind == "str" else 15
        flag = 256 if kind == "str" else 512 + 6
        fdesc += struct.pack("<20sBihhih4x", nb, t, pos, decl, w2, flag, len(layout))
        layout.append((kind, width, pos))
        pos += width
    reclen = pos
    recs = b""
    for r in rows:
        rec = bytearray(reclen)
        rec[0] = 0x01
        for (kind, width, p), v in zip(layout, r):
            if kind == "str":
                s = str(v).encode("gbk")[:width - 1]
                rec[p:p + len(s)] = s
            elif kind == "double":
                rec[p:p + 8] = struct.pack("<d", float(v))
            elif kind == "int":
                rec[p:p + 4] = struct.pack("<i", int(v))
            elif kind == "byte":
                rec[p] = int(v)
            elif kind == "short":
                rec[p:p + 2] = struct.pack("<h", int(v))
            elif kind == "float":
                rec[p:p + 4] = struct.pack("<f", float(v))
        recs += bytes(rec)
    empty = bytearray(reclen); empty[0] = 0x01
    head = (prefix_template[:322] if prefix_template and len(prefix_template) >= 322
            else bytes(322))
    body = head + struct.pack("<h", len(fields)) + struct.pack("<i", len(rows) + 1) + \
        struct.pack("<h", reclen) + bytes(18) + fdesc + bytes(empty) + recs
    return body


def write_wt(path, points, fields=(), rows=(), template=None, symbol=48,
             size=2.0, color=1, layer=0, pen=0.1):
    """写出 MapGIS .WT 点文件
    points: [(x_mm, y_mm), ...]
    fields/rows: 属性表（可空，空则写 1 个 ID 整数字段）
    template: 现有 .WT 文件路径或 657 字节头，用于继承坐标系/常数块
    """
    if template is None:
        head = bytearray(DATA_START)          # 必须是 657 字节，否则索引区错位
        head[0:8] = T_MAGIC
        struct.pack_into("<i", head, 8, 1)
        struct.pack_into("<i", head, 12, DATA_START)
        struct.pack_into("<d", head, 143, 0.0)
        struct.pack_into("<2d", head, 244, 1.0, 1.0)
        head[336] = 0x80
    else:
        src = open(template, "rb").read() if isinstance(template, str) else template
        head = bytearray(src[:DATA_START])
        attr_prefix = src
        try:
            idx, _ = _index(src)
            attr_prefix = src[idx[2][0]:idx[2][0] + 322]
        except Exception:
            attr_prefix = None

    pts = np.asarray(points, dtype=float)
    n = len(pts)
    struct.pack_into("<6I", head, 260, n, n + 1, 0, 0, 0, 0)
    struct.pack_into("<4d", head, 304, pts[:, 0].min(), pts[:, 1].min(),
                     pts[:, 0].max(), pts[:, 1].max())

    # --- 点记录区 (93B, 首条空)
    coord = bytearray(93)
    boxes = bytearray(32)          # 首条空标注框
    flags = bytearray(4)
    for (x, y) in pts:
        rec = bytearray(93)
        rec[0] = 1
        struct.pack_into("<d", rec, 7, x)
        struct.pack_into("<d", rec, 15, y)
        rec[31] = 1                                    # 1 = 子图点
        struct.pack_into("<h", rec, 33, symbol)
        struct.pack_into("<f", rec, 37, size)          # 高
        struct.pack_into("<f", rec, 41, size)          # 宽
        struct.pack_into("<f", rec, 45, 0.0)           # 旋转角
        struct.pack_into("<f", rec, 49, pen)           # 笔宽
        rec[75] = color
        rec[83] = layer
        coord += rec
        boxes += struct.pack("<4d", x - size / 2, y - size / 2, x + size / 2, y + size / 2)
        flags += struct.pack("<i", 65536)

    if not fields:
        fields = [("ID", "int", 4)]
        rows = [(i + 1,) for i in range(n)]
    attr = _attr_section(list(fields), list(rows),
                         prefix_template=locals().get("attr_prefix"))

    text_pool = bytes(2)
    sections = [bytes(coord), text_pool, attr, bytes(boxes), bytes(flags)]

    # --- 组装
    ds = DATA_START
    body_off = ds + 16 * 10
    idx_bytes = bytearray()
    cur = body_off
    for data in sections:
        idx_bytes += struct.pack("<2i", cur, len(data)) + b"\xff\xff"
        cur += len(data)
    for _ in range(16 - len(sections)):
        idx_bytes += struct.pack("<2i", 0, 0) + b"\xff\xff"
    out = bytes(head) + bytes(idx_bytes) + b"".join(sections)
    with open(path, "wb") as f:
        f.write(out)
    return out


# --------------------------------------------------------------- WL writer
def write_wl(path, polylines, ltype=1, aux=0, color=1, width=0.1, layer=0,
             xcoef=1.0, ycoef=1.0, template=None, attr_fields=None, attr_rows=None):
    """写出 MapGIS .WL 线文件（含 8 个索引段：线索引/坐标/属性/结点/55B/元数据/框表/标志）"""
    src = None
    if template:
        src = open(template, "rb").read()
        head = bytearray(src[:DATA_START])
        idx, _ = _index(src)
        h5 = src[idx[4][0]:idx[4][0] + idx[4][1]]
        meta = src[idx[5][0]:idx[5][0] + idx[5][1]]
        prefix = src[idx[2][0]:idx[2][0] + 322]
    else:
        head = bytearray(DATA_START)
        head[0:8] = W_MAGIC
        struct.pack_into("<i", head, 8, 0)
        struct.pack_into("<i", head, 12, DATA_START)
        struct.pack_into("<2d", head, 244, 1.0, 1.0)
        head[336] = 0
        h5, meta, prefix = bytes(55), bytes(392), None

    n = len(polylines)
    struct.pack_into("<6I", head, 260, n, n + 1, 0, 1, 0, 0)
    struct.pack_into("<3I", head, 284, n + 1, 0, 1)   # 与图框.WL 的头部计数序列一致
    allpts = np.vstack([np.asarray(p, float) for p in polylines])
    struct.pack_into("<4d", head, 304, allpts[:, 0].min(), allpts[:, 1].min(),
                     allpts[:, 0].max(), allpts[:, 1].max())

    lsec = bytearray(57)                     # 首条空记录
    csec = bytearray(2)                      # 坐标区 2B 前导
    bsec = bytearray(32)                     # 首条空框
    fsec = bytearray(4)
    off = 2                                  # 坐标区有 2 字节前导，第一线的偏移从 2 起
    for xy in polylines:
        xy = np.asarray(xy, dtype=float)
        rec = bytearray(57)
        rec[0], rec[1] = 1, 2
        struct.pack_into("<i", rec, 10, len(xy))
        struct.pack_into("<i", rec, 14, off)
        struct.pack_into("<h", rec, 22, ltype)
        struct.pack_into("<h", rec, 24, aux)
        struct.pack_into("<h", rec, 26, color)
        struct.pack_into("<f", rec, 30, width)
        struct.pack_into("<f", rec, 35, xcoef)
        struct.pack_into("<f", rec, 39, ycoef)
        struct.pack_into("<h", rec, 43, color)
        rec[47] = layer
        lsec += rec
        csec += xy.astype("<f8").tobytes()
        off += len(xy) * 16
        bsec += struct.pack("<4d", xy[:, 0].min(), xy[:, 1].min(),
                            xy[:, 0].max(), xy[:, 1].max())
        fsec += struct.pack("<i", 65536)

    nsec = bytes(24 * (n + 1))
    if attr_fields is None:
        attr = _attr_section([("ID", "int", 4)], [(i + 1,) for i in range(n)],
                             prefix_template=prefix)
    else:
        attr = _attr_section(attr_fields, attr_rows, prefix_template=prefix)

    sections = [bytes(lsec), bytes(csec), attr, nsec, bytes(h5), bytes(meta),
                bytes(bsec), bytes(fsec)]
    ds = DATA_START
    cur = ds + 16 * 10
    idxb = bytearray()
    for data in sections:
        idxb += struct.pack("<2i", cur, len(data)) + b"\xff\xff"
        cur += len(data)
    for _ in range(16 - len(sections)):
        idxb += struct.pack("<2i", 0, 0) + b"\xff\xff"
    out = bytes(head) + bytes(idxb) + b"".join(sections)
    with open(path, "wb") as f:
        f.write(out)
    return out


# ------------------------------------------------------- WT 注记点写出
_ANNOT_POOL_HEAD = 1602          # 文本池固定前缀长度（实测 地质.WT/图框.WT 均为 1602）


def _annot_pool_head(template):
    """从真实点文件里取文本池的 1602 字节前缀（字体/样式块，原样克隆最安全）"""
    if not template:
        return bytes(_ANNOT_POOL_HEAD)
    b = open(template, "rb").read()
    idx, _ = _index(b)
    tstart, tvol = idx[1]
    head = b[tstart:tstart + min(_ANNOT_POOL_HEAD, tvol)]
    return head + bytes(max(0, _ANNOT_POOL_HEAD - len(head)))


def write_wt_annot(path, items, template=None, fields=None, rows=None):
    """写出"注记点"（文字点）的 .WT
    items: [dict(x, y, text, h=2.0, w=2.0, gap=0.1, angle=0.0, color=1, layer=0,
                 cnfont=2, enfont=2, style=0)]
    点记录（93B）: [1B 标志][u16 文本字节数][u32 文本在池中的偏移][f64 X][f64 Y][70B 参数]
    文本池: [1602B 样式前缀][逐条 GBK 文本首尾相接]
    """
    if template:
        src = open(template, "rb").read()
        head = bytearray(src[:DATA_START])
        idx, _ = _index(src)
        prefix = src[idx[2][0]:idx[2][0] + 322]
    else:
        head = bytearray(DATA_START)
        head[0:8] = T_MAGIC
        struct.pack_into("<i", head, 8, 1)
        struct.pack_into("<i", head, 12, DATA_START)
        struct.pack_into("<2d", head, 244, 1.0, 1.0)
        head[336] = 0x80
        prefix = None

    n = len(items)
    struct.pack_into("<6I", head, 260, n, n + 1, 0, 0, 0, 0)
    xs = [it["x"] for it in items]; ys = [it["y"] for it in items]
    struct.pack_into("<4d", head, 304, min(xs), min(ys), max(xs), max(ys))

    pool = bytearray(_annot_pool_head(template))
    coord = bytearray(93)          # 首条空记录
    boxes = bytearray(32)
    flags = bytearray(4)
    for it in items:
        txt = str(it["text"]).encode("gbk")
        off = len(pool)
        pool += txt
        h = float(it.get("h", 2.0)); w = float(it.get("w", 2.0))
        gap = float(it.get("gap", 0.1)); ang = float(it.get("angle", 0.0))
        rec = bytearray(93)
        rec[0] = 1
        struct.pack_into("<H", rec, 1, len(txt))
        struct.pack_into("<I", rec, 3, off)
        struct.pack_into("<d", rec, 7, it["x"])
        struct.pack_into("<d", rec, 15, it["y"])
        rec[31] = 0                                  # 0 = 注释点（文字）
        struct.pack_into("<f", rec, 33, h)
        struct.pack_into("<f", rec, 37, w)
        struct.pack_into("<f", rec, 41, gap)
        struct.pack_into("<f", rec, 45, ang)
        rec[49] = int(it.get("cnfont", 2))
        rec[51] = int(it.get("enfont", 2))
        rec[53] = int(it.get("style", 0))
        rec[75] = int(it.get("color", 1))
        rec[83] = int(it.get("layer", 0))
        coord += rec
        nch = max(1, len(str(it["text"])))
        tw = nch * (w * 0.95 + gap)
        boxes += struct.pack("<4d", it["x"], it["y"] - h * 0.35,
                             it["x"] + tw, it["y"] + h * 0.95)
        flags += struct.pack("<i", 65536)

    if fields is None:
        fields = [("ID", "int", 4)]
        rows = [(i + 1,) for i in range(n)]
    attr = _attr_section(list(fields), list(rows), prefix_template=prefix)

    sections = [bytes(coord), bytes(pool), attr, bytes(boxes), bytes(flags)]
    cur = DATA_START + 16 * 10
    idxb = bytearray()
    for data in sections:
        idxb += struct.pack("<2i", cur, len(data)) + b"\xff\xff"
        cur += len(data)
    for _ in range(16 - len(sections)):
        idxb += struct.pack("<2i", 0, 0) + b"\xff\xff"
    out = bytes(head) + bytes(idxb) + b"".join(sections)
    with open(path, "wb") as f:
        f.write(out)
    return out


def read_wt_annot(path):
    """回读注记点：返回 [(x, y, text, h, w, gap, angle, color, layer)]"""
    b = open(path, "rb").read()
    idx, _ = _index(b)
    cstart, cvol = idx[0]
    tstart, tvol = idx[1]
    n = cvol // 93 - 1
    out = []
    for i in range(1, n + 1):
        off = cstart + i * 93
        ln = struct.unpack_from("<H", b, off + 1)[0]
        toff = struct.unpack_from("<I", b, off + 3)[0]
        x, y = struct.unpack_from("<2d", b, off + 7)
        txt = b[tstart + toff: tstart + toff + ln].decode("gbk", "replace")
        out.append((x, y, txt,
                    struct.unpack_from("<f", b, off + 33)[0],
                    struct.unpack_from("<f", b, off + 37)[0],
                    struct.unpack_from("<f", b, off + 41)[0],
                    struct.unpack_from("<f", b, off + 45)[0],
                    b[off + 75], b[off + 83]))
    return out


def read_wt_attrs(path):
    """读取 .WT 的属性表 -> (字段列表, 记录列表)
    字段: [(name, type, pos, width)]；记录: list[dict]
    """
    b = open(path, "rb").read()
    idx, _ = _index(b)
    a = idx[2][0]
    nf = struct.unpack_from("<h", b, a + 322)[0]
    nr = struct.unpack_from("<i", b, a + 324)[0]
    rl = struct.unpack_from("<h", b, a + 328)[0]
    fields = []
    for k in range(nf):
        o = a + 348 + 39 * k
        name = b[o:o + 20].split(b"\x00")[0].decode("gbk", "ignore")
        typ = b[o + 20]
        pos = struct.unpack_from("<i", b, o + 21)[0]
        w1 = struct.unpack_from("<h", b, o + 25)[0]
        fields.append((name, typ, pos, w1))
    base = a + 348 + 39 * nf
    rows = []
    for i in range(nr):
        rec = b[base + i * rl: base + (i + 1) * rl]
        if len(rec) < rl:
            break
        d = {}
        for (name, typ, pos, width) in fields:
            w = width
            if typ == 0:
                d[name] = rec[pos:pos + w].split(b"\x00")[0].decode("gbk", "ignore")
            elif typ == 1:
                d[name] = rec[pos]
            elif typ == 2:
                d[name] = struct.unpack_from("<h", rec, pos)[0]
            elif typ == 3:
                d[name] = struct.unpack_from("<i", rec, pos)[0]
            elif typ == 4:
                d[name] = struct.unpack_from("<f", rec, pos)[0]
            elif typ == 5:
                d[name] = struct.unpack_from("<d", rec, pos)[0]
            else:
                d[name] = rec[pos:pos + w]
        rows.append(d)
    return fields, rows


def read_wt(path):
    b = open(path, "rb").read()
    idx, ds = _index(b)
    (cstart, cvol) = idx[0]
    n = cvol // 93 - 1
    pts = []
    for i in range(1, n + 1):
        off = cstart + i * 93
        x, y = struct.unpack_from("<2d", b, off + 7)
        pts.append((x, y, b[off + 31], struct.unpack_from("<h", b, off + 33)[0]))
    return pts, b
