# -*- coding: utf-8 -*-
r"""字节级回归：用本库重写真实交付文件，与原件做 SHA-256 比对。

    python scripts/selftest.py              # 真实交付文件回归（需样本，缺则 SKIP）
    python scripts/selftest.py --fixture    # 用入库的最小样本回归（任何机器可跑）

这是本技能唯一的「保真度」证据：只要 5 个文件全 PASS，说明写入器与原件的字节布局一致，
比任何「结构自检通过」都硬。改写入逻辑后必须先跑通这个。

样本是**你自己的项目文件**，不在仓库里；缺文件时该项自动 SKIP（不算失败），
所以别人 clone 下来跑也不会红，只是没有任何项目被真实验证 —— 这一步只能你自己跑。
"""
import os, sys, csv, hashlib, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapgis_native import Skeleton, write_points, write_labels, write_lines, read, verify, subscript

BASE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Administrator\Desktop\地球化学勘查"
OUT  = os.path.join(BASE, "02_阶段一_采样点位图", "合并成果")
TPL_POINT = os.path.join(BASE, "02_阶段一_采样点位图", "控制点.WT")
TPL_LABEL = r"C:\Users\Administrator\Desktop\地球化学勘查设计\2026课程设计下发资料\图2xxx水系材料图\图框.WT"

CF = [("点号", 0, 13, 12, 256), ("单元", 3, 4, 15, 512), ("小格", 0, 5, 4, 256), ("序号", 3, 4, 15, 512),
      ("X_m", 5, 8, 15, 518), ("Y_m", 5, 8, 15, 518), ("类型", 0, 17, 16, 256), ("连续号", 3, 4, 15, 512)]
RF = [("点号", 0, 13, 12, 256), ("对应点号", 0, 13, 12, 256), ("单元", 3, 4, 15, 512), ("小格", 0, 5, 4, 256),
      ("X_m", 5, 8, 15, 518), ("Y_m", 5, 8, 15, 518), ("类型", 0, 17, 16, 256), ("连续号", 3, 4, 15, 512)]


class Skip(Exception):
    pass


def need(*paths):
    miss = [p for p in paths if not os.path.exists(p)]
    if miss:
        raise Skip("缺少样本: %s" % os.path.basename(miss[0]) + (" 等 %d 个" % len(miss) if len(miss) > 1 else ""))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


def rows_from_csv():
    p = os.path.join(OUT, "采样点位主表.csv")
    need(p)
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _roundtrip(tmp, name, fields, symbol, color, layer):
    """读原件 -> 用库重写 -> 与原文件逐字节比对（验证写入器保真度）。"""
    src_path = os.path.join(OUT, name)
    need(src_path, TPL_POINT)
    src = read(src_path)
    recs = []
    for r in src["records"]:
        d = {f[0]: r.get(f[0]) for f in fields}
        d["X"], d["Y"] = r["X"], r["Y"]
        recs.append(d)
    sk = Skeleton.from_file(TPL_POINT)
    p = os.path.join(tmp, name)
    write_points(p, sk, recs, fields, symbol=symbol, color=color, layer=layer,
                 x_key="X", y_key="Y", attr_sk=sk)
    return p, src_path


def t_control(tmp):
    return _roundtrip(tmp, "控制点_合并.WT", CF, 48, 134, 0)


def t_repeat(tmp):
    return _roundtrip(tmp, "重复样_同点.WT", RF, 84, 96, 11)


def t_labels(tmp):
    src_path = os.path.join(OUT, "控制点_合并.WT")
    need(src_path, TPL_LABEL)
    src = read(src_path)
    items = []
    for r in src["records"]:
        t = subscript("%s%s" % (r["小格"], r["序号"]))
        items.append(dict(x=r["X"] + 0.7, y=r["Y"] - 0.35, text=t, attr=r["点号"],
                          vis=len(t.replace("#-", ""))))
    sk = Skeleton.from_file(TPL_LABEL)
    kp = Skeleton.from_file(src_path)
    p = os.path.join(tmp, "lbl.WT")
    write_labels(p, sk, items, height=1.2, width=1.0, gap=0.05, color=1, layer=12, attr_sk=kp)
    return p, os.path.join(OUT, "点号注记_小格号.WT")


def t_grid(tmp):
    src_path = os.path.join(OUT, "控制点_合并.WT")
    need(src_path, TPL_LABEL)
    items = []
    for j in range(18):
        for i in range(25):
            u = j * 25 + i + 1
            cx, cy = 10510 + 20 * i, 57150 - 20 * j
            items.append(dict(x=cx - 2.5, y=cy - 1.0, text="%03d" % u, attr="%03d" % u))
    sk = Skeleton.from_file(TPL_LABEL)
    kp = Skeleton.from_file(src_path)
    p = os.path.join(tmp, "grid.WT")
    write_labels(p, sk, items, height=2.0, width=1.6, gap=0.05, color=1, layer=13,
                 field="单元", attr_sk=kp)
    return p, os.path.join(OUT, "大格号_001_450.WT")


def t_legend(tmp):
    # 骨架取目标文件自身：500m小格线.WL 会被人在 MAPGIS 里重新生成（2026-11-27 就变过一次），
    # 拿它当模板会让字节比对随模板漂移而假红；自骨架只验证写入器自身可复现。
    want = os.path.join(OUT, "图例_线.WL")
    need(want)
    sk = Skeleton.from_file(want)
    return _legend(tmp, sk, want)


def _legend(tmp, sk, want):
    LX, RX, YBOT, YTOP = 11016, 11072, 56989, 57066
    SX0, SX1 = LX + 2.5, LX + 10.5
    I3, I4, I5, I6, I7 = 57021, 57014, 57007, 57000, 56993
    segs = [([(LX, YBOT), (RX, YBOT), (RX, YTOP), (LX, YTOP), (LX, YBOT)], (1, 1, 0.20)),
            ([(SX0, 57055), (SX1 + 44, 57055)], (1, 1, 0.10)),
            ([(SX0, I3 + 0.2), (SX1, I3 + 0.2)], (1, 2, 0.28)),
            ([(SX0, I4 + 0.2), (SX1, I4 + 0.2)], (1, 154, 0.08)),
            ([(SX0, I5 + 0.2), (SX1, I5 + 0.2)], (1, 154, 0.30))]
    for x0 in [0, 1.6, 3.2, 4.8, 6.4]:
        segs.append(([(SX0 + x0, I6 + 0.2), (SX0 + x0 + 1.0, I6 + 0.2)], (1, 1, 0.08)))
    segs.append(([(SX0, I7 + 0.2), (SX1, I7 + 0.2)], (1, 1, 0.20)))
    p = os.path.join(tmp, "legend.WL")
    write_lines(p, sk, segs)
    return p, want


TESTS = [("控制点_合并.WT", t_control), ("重复样_同点.WT", t_repeat),
         ("点号注记_小格号.WT", t_labels), ("大格号_001_450.WT", t_grid),
         ("图例_线.WL", t_legend)]


def fixture_suite():
    """golden 回归：用入库的 3 个最小样本自证写入器没被改坏。任何机器可跑。"""
    tests_dir = os.path.normpath(os.path.join(HERE, "..", "tests"))
    sys.path.insert(0, tests_dir)
    import make_fixtures as mf

    fix = mf.FIX
    names = ["demo_points.WT", "demo_labels.WT", "demo_lines.WL"]
    tmp = tempfile.mkdtemp(prefix="mg_golden_")
    mf.build(tmp,
             Skeleton.from_file(os.path.join(fix, "demo_points.WT")),
             Skeleton.from_file(os.path.join(fix, "demo_labels.WT")),
             Skeleton.from_file(os.path.join(fix, "demo_lines.WL")))

    ok = fail = 0
    for name in names:
        got, want = sha(os.path.join(tmp, name)), sha(os.path.join(fix, name))
        if got == want:
            ok += 1
            v = verify(os.path.join(fix, name))
            print("PASS %-18s %s  (%d B, units=%d, ok=%s)" %
                  (name, want, v["bytes"], v["units"], v["ok"]))
        else:
            fail += 1
            print("FAIL %-18s got=%s want=%s" % (name, got, want))
    print("\n%d PASS / %d FAIL（golden 样本；只证写入器未变，不证 MAPGIS 兼容性）" % (ok, fail))
    return 1 if fail else 0


def main():
    if "--fixture" in sys.argv[1:]:
        return fixture_suite()
    tmp = tempfile.mkdtemp(prefix="mg_test_")
    ok = skip = fail = 0
    for name, fn in TESTS:
        try:
            got, want = fn(tmp)
        except Skip as e:
            skip += 1
            print("SKIP %-20s %s" % (name, e))
            continue
        except Exception as e:
            fail += 1
            print("ERROR %-20s %s" % (name, e))
            continue
        a, b = sha(got), sha(want)
        if a == b:
            ok += 1
            v = verify(got)
            print("PASS %-20s %s  (%d B, units=%d, ok=%s)" %
                  (name, a, v["bytes"], v["units"], v["ok"]))
        else:
            fail += 1
            print("FAIL %-20s got=%s want=%s" % (name, a, b))
            print("     verify:", verify(got))
    print("\n%d PASS / %d SKIP / %d FAIL（共 %d）" % (ok, skip, fail, len(TESTS)))
    if skip == len(TESTS):
        print("全部 SKIP：没找到样本文件。传项目根目录，或先按 SKILL.md 造一份对照样本。")
        return 0
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())