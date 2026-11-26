# -*- coding: utf-8 -*-
"""
自检：不依赖 MAPGIS、不依赖任何样例文件，现场造出 .WT / .WL / 注记层再读回校验。
用法： python scripts/demo_selftest.py [输出目录]
全部通过会打印 PASS x N；任何一项不符直接 AssertionError 退出。
"""
import sys, os, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapgis_wl import (write_wt, read_wt, read_wt_attrs,
                       write_wl, read_wl, write_wt_annot, read_wt_annot)

out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="mapgis_selftest_")
os.makedirs(out, exist_ok=True)
ok = 0
print("输出目录:", out)

# ---------------------------------------------------------------- 1. 点文件
wt = os.path.join(out, "points.WT")
pts = [(10500.0, 56800.0), (10520.0, 56800.0), (10520.0, 56820.0),
       (10500.0, 56820.0), (10510.0, 56810.0)]
rows = [("001A1", 1, "A", 10500.0, 56800.0, 1, "一级水系下游"),
        ("001B1", 1, "B", 10520.0, 56800.0, 1, "一级水系下游"),
        ("001C1", 1, "C", 10520.0, 56820.0, 2, "小格补齐"),
        ("001D1", 1, "D", 10500.0, 56820.0, 2, "小格补齐"),
        ("002A1", 2, "A", 10510.0, 56810.0, 1, "一级水系下游")]
fields = [("点号", "str", 12), ("单元", "int", 4), ("小格", "str", 4),
          ("X_m", "double", 8), ("Y_m", "double", 8),
          ("Strahler", "int", 4), ("类型", "str", 16)]
write_wt(wt, pts, fields=fields, rows=rows, template=None, symbol=48, size=2.0)
back, raw = read_wt(wt)
assert len(back) == 5, len(back)
assert abs(back[0][0] - 10500.0) < 1e-9 and abs(back[4][1] - 56810.0) < 1e-9
assert all(b[3] == 48 for b in back), "子图号应为 48"
assert raw[:8] == b"WMAP`D22", "魔数必须是点文件"
ok += 1; print("PASS 1  .WT 写入/回读     点数=%d 子图号=%d" % (len(back), back[0][3]))

# ---------------------------------------------------------------- 2. 属性表
f, r = read_wt_attrs(wt)
assert [x[0] for x in f] == [x[0] for x in fields]
assert len(r) == len(pts) + 1, "记录数应为 点数+1（首条空）"
assert r[1]["点号"] == "001A1" and r[5]["Strahler"] == 1
assert r[3]["类型"] == "小格补齐", r[3]["类型"]       # 中文不能被截断
ok += 1; print("PASS 2  属性表读写       %d 字段 / %d 记录, 中文完整" % (len(f), len(r)))

# ---------------------------------------------------------------- 3. 线文件
wl = os.path.join(out, "grid.WL")
lines = [((10500.0, 56800.0), (10520.0, 56800.0)),
         ((10500.0, 56820.0), (10520.0, 56820.0)),
         ((10510.0, 56800.0), (10510.0, 56820.0))]
write_wl(wl, [ [a, b] for a, b in lines ], ltype=2, color=1, width=0.1, layer=10,
         template=None)
lback = read_wl(wl)
assert len(lback) == 3, len(lback)
assert abs(lback[0]["xy"][0][0] - 10500.0) < 1e-9, "坐标错位 → 检查坐标区 2 字节前导"
assert lback[1]["xy"][1][1] == 56820.0
assert all(l["ltype"] == 2 and l["layer"] == 10 for l in lback)
ok += 1; print("PASS 3  .WL 写入/回读     线=%d 线型号=2 图层=10" % len(lback))

# ---------------------------------------------------------------- 4. 注记点
ann = os.path.join(out, "labels.WT")
items = [dict(x=10502.0, y=56802.0, text="001", h=2.0, w=2.0, gap=0.1, color=1),
         dict(x=10522.0, y=56802.0, text="002", h=2.0, w=2.0, gap=0.1, color=1),
         dict(x=10502.0, y=56822.0, text="A1", h=1.3, w=1.1, gap=0.05, color=6)]
write_wt_annot(ann, items, template=None,
               fields=[("文字", "str", 12)], rows=[(it["text"],) for it in items])
aback = read_wt_annot(ann)
assert [a[2] for a in aback] == ["001", "002", "A1"], [a[2] for a in aback]
assert abs(aback[0][3] - 2.0) < 1e-6 and aback[2][7] == 6
b2 = open(ann, "rb").read()
assert b2[:8] == b"WMAP`D22"
ok += 1; print("PASS 4  注记点读写       %d 条, 文本/字号/颜色均正确" % len(aback))

# ---------------------------------------------------------------- 5. 结构自检
import struct
def sections(path):
    b = open(path, "rb").read()
    ds = struct.unpack_from("<i", b, 12)[0]
    return [(struct.unpack_from("<2i", b, ds + 10*i)) for i in range(16)], b, ds
idx, b, ds = sections(ann)
cvol = idx[0][1]; tvol = idx[1][1]
n = cvol // 93 - 1
textlen = sum(len(it["text"].encode("gbk")) for it in items)
assert tvol == 1602 + textlen, (tvol, 1602 + textlen)
assert idx[3][1] == (n + 1) * 32, "标注框段应为 (n+1)*32"
assert idx[4][1] == 4 + 4 * n, "标志段应为 4+4n"
ok += 1; print("PASS 5  段长自检         文本池=%d(=1602+%d) 框表=%d 标志=%d"
               % (tvol, textlen, idx[3][1], idx[4][1]))

print("\n全部通过（%d 项）。生成的文件在 %s，可用 MapGIS 打开目视确认符号/字号。" % (ok, out))
