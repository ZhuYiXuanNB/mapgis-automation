# -*- coding: utf-8 -*-
r"""生成最小回归样本（golden files）。

**只在有真实 MAPGIS 文件的机器上跑一次**，产物已入库，其他人不需要跑：

    python tests/make_fixtures.py --point 控制点.WT --label 图框.WT --wl 500m小格线.WL

样本 = 3 点 + 3 注记 + 2 条线，约 8 KB。作用是把「骨架来自真实 MAPGIS 文件」
这件事固定在仓库里，让 `selftest.py --fixture` 能在任何机器上跑回归。

⚠️ 它证明的是「写入器没被改坏」（golden 比对），**不证明** MAPGIS 兼容性 ——
后者只有真实交付文件的字节级回归（`selftest.py` 不带参数）能证。
"""
import os, sys, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from mapgis_native import Skeleton, write_points, write_labels, write_lines

FIX = os.path.join(HERE, "fixtures")

FIELDS = [("点号", 0, 13, 12, 256), ("类型", 0, 17, 16, 256),
          ("X", 5, 8, 15, 518), ("Y", 5, 8, 15, 518)]

POINTS = [dict(点号="001A1", 类型="完整单元", X=10503.670319, Y=57158.267434),
          dict(点号="001A2", 类型="完整单元", X=10508.101404, Y=57150.804576),
          dict(点号="002A1", 类型="重复样",   X=10512.500000, Y=57140.000000)]

LABELS = [dict(x=10504.37, y=57157.92, text="001A#-1", attr="001A1", vis=5),
          dict(x=10508.80, y=57150.45, text="001A#-2", attr="001A2", vis=5),
          dict(x=10513.20, y=57139.65, text="002A#-1", attr="002A1", vis=5)]

LINES = [([(10500.0, 57160.0), (10560.0, 57160.0)], (1, 1, 0.2)),
         ([(10500.0, 57170.0), (10500.0, 57110.0), (10540.0, 57110.0)], (2, 2, 0.3))]


def build(out, sk_point, sk_label, sk_wl):
    """用给定骨架生成三个样本文件，返回 {文件名: 字节数}。"""
    os.makedirs(out, exist_ok=True)
    r = write_points(os.path.join(out, "demo_points.WT"), sk_point, POINTS, FIELDS,
                     symbol=48, color=134, layer=0, height=1.5, width=1.5, half=1.5,
                     x_key="X", y_key="Y", attr_sk=sk_point)
    write_labels(os.path.join(out, "demo_labels.WT"), sk_label, LABELS,
                 height=1.2, width=1.0, gap=0.05, color=1, layer=12,
                 field="点号", attr_sk=sk_point)
    write_lines(os.path.join(out, "demo_lines.WL"), sk_wl, LINES)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--point", required=True, help="任一点 .WT（只用它做骨架）")
    ap.add_argument("--label", required=True, help="任一注记 .WT")
    ap.add_argument("--wl", required=True, help="任一 .WL")
    a = ap.parse_args()
    sk_p = Skeleton.from_file(a.point)
    sk_l = Skeleton.from_file(a.label)
    sk_w = Skeleton.from_file(a.wl)
    r = build(FIX, sk_p, sk_l, sk_w)
    print("已生成:", r)
    print("文件:", sorted(os.listdir(FIX)))


if __name__ == "__main__":
    main()