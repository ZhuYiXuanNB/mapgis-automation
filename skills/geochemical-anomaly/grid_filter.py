# -*- coding: utf-8 -*-
"""
网格预处理：3×3 中值滤波 + 剔除小于 N 格的孤立斑块，输出 MAPGIS 可直接读的 .GRD。

用途：等值线成图前去掉网格化产生的单点尖峰与零散碎斑，
让异常"少而完整"。阈值本身不改，只清理噪声。

用法：
    python grid_filter.py in.GRD out.GRD --threshold 2.902 --min-cells 12
    python grid_filter.py in.GRD out.GRD --threshold 15.81 --min-cells 20 --no-median

.GRD 格式（实测）：
    0-3    b"DSBB"
    4-5    int16 nx
    6-7    int16 ny
    8-47   5 个 double: xmin, xmax, ymin, ymax, nodata
    48-55  保留
    56-    nx*ny 个 float32，行序自 ymin 起
"""
import argparse
import struct
from collections import deque

import numpy as np


def read_grd(path):
    raw = open(path, "rb").read()
    if raw[:4] != b"DSBB":
        raise ValueError("不是 MAPGIS GRD 文件: " + path)
    nx, ny = struct.unpack("<hh", raw[4:8])
    xmin, xmax, ymin, ymax, nodata = struct.unpack("<5d", raw[8:48])
    grid = np.frombuffer(raw[56:], dtype="<f4").reshape(ny, nx).astype(np.float32)
    return grid, (xmin, xmax, ymin, ymax, nodata)


def write_grd(path, grid, header):
    xmin, xmax, ymin, ymax, nodata = header
    hdr = bytearray(b"DSBB")
    hdr += struct.pack("<hh", grid.shape[1], grid.shape[0])
    hdr += struct.pack("<5d", xmin, xmax, ymin, ymax, nodata)
    hdr += b"\x00" * 8
    open(path, "wb").write(bytes(hdr[:56]) + grid.astype("<f4").tobytes())


def median3(g):
    out = g.copy()
    h, w = g.shape
    for i in range(1, h - 1):
        for j in range(1, w - 1):
            out[i, j] = np.median(g[i - 1:i + 2, j - 1:j + 2])
    return out


def drop_small(g, threshold, min_cells):
    h, w = g.shape
    mask = g >= threshold
    seen = np.zeros((h, w), bool)
    kept = removed = 0
    for i in range(h):
        for j in range(w):
            if not mask[i, j] or seen[i, j]:
                continue
            q = deque([(i, j)])
            seen[i, j] = True
            cells = [(i, j)]
            while q:
                y, x = q.popleft()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        q.append((yy, xx))
                        cells.append((yy, xx))
            if len(cells) < min_cells:
                for (y, x) in cells:
                    g[y, x] = np.float32(threshold - 0.001 * abs(threshold))
                removed += 1
            else:
                kept += 1
    print(f"  保留斑块 {kept}，剔除 {removed}")
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--threshold", type=float, required=True, help="异常下限（据此判定斑块）")
    ap.add_argument("--min-cells", type=int, default=12, help="小于该格数的斑块被剔除")
    ap.add_argument("--no-median", action="store_true", help="跳过 3x3 中值滤波")
    args = ap.parse_args()

    g, header = read_grd(args.src)
    if not args.no_median:
        g = median3(g)
    g = drop_small(g, args.threshold, args.min_cells)
    write_grd(args.dst, g, header)
    print(f"已写出 {args.dst}  阈值={args.threshold} 面积占比={(g >= args.threshold).mean() * 100:.2f}%")


if __name__ == "__main__":
    main()
