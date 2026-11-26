---
name: mapgis-vector-io
description: "用纯 Python 读写 MAPGIS 6.7 矢量文件（.WT 点 / .WL 线 / .WP 面）：解析坐标、增删改属性字段、按属性批量生成注记点（点号、大格编号）、批量改子图号。当需要生成点位图/格网线、给点文件挂属性、把属性写成图面注记、或校验 MAPGIS 文件结构时使用；不涉及 MAPGIS 桌面操作。"
---

# MAPGIS 点线面文件读写：属性、注记与批量生成

> 配套：字节级细节看 `reference/format.md`，踩坑清单看 `reference/pitfalls.md`，
> 仓库根目录 `docs/binary-format.md` 是更早一版实测记录（可交叉印证）。
> 需要**操作 MAPGIS 桌面**（网格化、等值线、出图）时，用根目录的 `mapgis-automation` 技能。

## 0. 何时用 / 何时不用

| 用本技能 | 不用本技能 |
|---|---|
| 把采样点表（CSV/Excel）变成 `.WT` | 要在 MAPGIS 里做网格化、等值线、空间分析 |
| 给现成 `.WT` 加字段、改属性值 | 要驱动 MAPGIS 菜单/对话框 |
| 由属性生成注记（点号、大格编号） | 需要 MAPGIS 内部拓扑检查/构区 |
| 生成格网 `.WL`、读水系做分级 | |
| 校验文件能不能被 MAPGIS 打开 | |

## 1. 30 秒上手

```bash
# 自检：不依赖 MAPGIS、不依赖样例，现场造 WT/WL/注记再读回（5 项断言）
python scripts/demo_selftest.py out/

# 属性导出 / 就地改
python scripts/wt_attrs.py dump --wt points.WT --out attrs.csv
python scripts/wt_attrs.py set  --wt points.WT --where Strahler=1 --set 类型=必采

# 改子图号（只动符号，不动其它字节）
python scripts/set_symbol.py points.WT --symbol 48 --size 2.0
```

```python
import sys; sys.path.insert(0, "scripts")
from mapgis_wl import (read_wl, write_wl, read_wt, write_wt,
                       read_wt_attrs, write_wt_annot, read_wt_annot)
```

## 2. 三条铁律（先看，能省 90% 的调试时间）

1. **文件头 657 B 直接从真实文件克隆**，别自己造。头里除了魔数还有毫米→度系数（@244/@252）、
   图幅边界框（@304）、比例尺（@143）等"显示闸门"，造错会"能读不能显示"。
   做法：`write_wt(..., template="任一真实.WT")`。
2. **索引区固定 16 项 × 10 B**，每项 `<int32 start><int32 volume><2B 0xFFFF>`；
   没用到的段也要写 `(0,0,0xFFFF)`。段的顺序就是索引号，缺段会在 MapGIS 里丢东西。
3. **每段首条记录都是空的**：
   - 点数 = `idx0.volume / 93 - 1`
   - 线/弧数 = `idx0.volume / 57 - 1`
   - 属性记录数 = 点数 + 1
   少写这条空记录，MapGIS 里属性和点位会**错开一行**。

### 2.1 旧文档说"手工拼装一律失败"，为什么现在行

`docs/binary-format.md` 早期版本的结论是"不要手工拼装，MAPGIS 一律拒绝"。当时的排查其实已经找到根因：
生成文件与可显示模板**前 817 字节只差 20 字节**，差的正是三个被清空的附属段指针
（+20/+24 属性段、+40/+44 附加表 A、+60/+64 附加表 B）——**是缺段，不是拒绝手工文件**。

所以现在的规则是：

| 类型 | 必须齐全的段 | 缺了会怎样 |
|---|---|---|
| `.WT` | 0 记录 / 1 文本池 / 2 属性 / 3 标注框 / 4 标志 | 能解析、不显示 |
| `.WL` | 0 线索引 / 1 坐标 / 2 属性 / 3 结点表 / 4 55B / 5 元数据 / 6 框表 / 7 标志 | 能解析、不显示 |

`write_wt`/`write_wl` 在 `template=None` 时会补零段并**打印警告**；正式生成请一律给真实模板。
**已实测验收**（2026-11-26，SECTION V5.6 + 编辑子系统）：点符号、注记文字（含中文）、字号、颜色、位置全部正常，
详见 [`docs/verification.md`](../../docs/verification.md)。换机器或换 Slib 版本后仍需再确认一次。

## 3. 骨架一张表

```
[657B 头][16×10B 索引][段0][段1][段2]...
```

| 类型 | 段0 | 段1 | 段2 | 段3 | 段4 | 段5 | 段6 | 段7 |
|---|---|---|---|---|---|---|---|---|
| `.WT` | 点记录 93B | 文本池 | 属性 | 标注框 (n+1)×32 | 标志 4+4n | | | |
| `.WL` | 线索引 57B | 坐标 2B+16B/对 | 属性 | 结点表 24B | 55B | 元数据 392B | 框表 32B | 标志 4+4n |
| `.WP` | 弧索引 57B | 坐标(+结点表) | 元数据 | 拓扑 24B | 55B | 元数据 | 弧框表 | 标志 … 8=区参数 40B、9=属性、10=区标注框、12=文件脚 |

## 4. `.WT` 点文件

### 4.1 记录（93 B）

```
[0]      u8    恒 1
[1..6]   6B    保留（注记点另有含义，见 4.3）
[7..14]  f64   X
[15..22] f64   Y
[31]     u8    点种类：1=子图点  0=注记点(文字)
[33..36] f32   子图号(子图点) / 字高(注记)
[37..40] f32   高(子图点) / 字宽(注记)
[41..44] f32   宽(子图点) / 字间隔(注记)
[45..48] f32   旋转角（度）
[49..52] f32   笔宽 / 中文字体(u8@49)
[51]     u8    西文字体（注记）
[53]     u8    字形（注记）
[75]     u8    颜色号（colorlib 索引，1=黑）
[83]     u8    图层号
```

### 4.2 写子图点

```python
write_wt("pts.WT", [(x1, y1), (x2, y2)],
         fields=[("点号","str",12), ("Strahler","int",4)],
         rows=[("001A1",1), ("001A2",1)],
         template="参考.WT", symbol=48, size=2.0, color=1, layer=0)
```

- `symbol=48` 是本机 Slib 的**实心圆**；`symbol=1` 在本机是个怪符号（见 pitfalls 5）。
- `size` 是子图高/宽（mm），`1.5`–`2.5` 常用。

### 4.3 写注记点（文字）

```python
items = [dict(x=10502, y=56802, text="001", h=2.0, w=2.0, gap=0.1,
              angle=0, color=1, layer=0, cnfont=2, enfont=2)]
write_wt_annot("大格编号.WT", items, template="真实注记.WT")
```

注记点的前 7 字节换了含义：`[1..2]=文字字节数(u16)`、`[3..6]=文字在文本池中的偏移(u32)`；
**文本池 = 1602 B 固定样式前缀 + 逐条 GBK 首尾相接**，偏移从池首算（第一条=1602）。
第一件事就是克隆真实文件的 1602 B 前缀（`_annot_pool_head()` 已实现）。

**锚点 = 文字左下角**，文字向右上生长；标注框写 `(x, y-0.35h, x+字宽, y+0.95h)`，
少了框表 MapGIS 里"能读不显示"。

## 5. `.WL` 线文件

线索引 57 B：

```
[0]=01 [1]=02 [10..13] i32 顶点数 [14..17] i32 坐标偏移(相对坐标区首)
[22..23] i16 线型号  [24..25] i16 辅助线型号  [26..27] i16 颜色
[30..33] f32 线宽   [35..38] f32 X系数     [39..42] f32 Y系数
[43..44] i16 辅助色 [47] u8 图层          [48] u8 透明
```

```python
write_wl("grid.WL", [[(x0,y0),(x1,y1)], ...], ltype=2, color=1, width=0.1,
         layer=10, template="真实.WL")
```

> **坐标区有 2 字节前导**：第一条线的"坐标偏移"必须写 **2**，写 0 会让所有坐标整体错位 2 字节，
> 读出来是 `-1.4e+203` 之类的天文数字（本项目真踩过）。

## 6. `.WP` 面文件

结构同线文件，但多了：拓扑 24 B（`[结点a][结点b][左区][右区]`）、区参数 40 B
（`kind@0`、**类码@1 = 图层**、填充色@5、图案@6、图案色@9）、区标注框（段 10）、文件脚（段 12）。
**缺段 10/12 时区能解析但永不渲染**——做面文件请先读 `docs/binary-format.md`，或复制一个真实 `.WP` 改内容。

## 7. 属性表

```
[322B 前缀][i16 字段数][i32 记录数][i16 记录长][18B][39B×N 描述符][记录区]
```

39 B 描述符：`名称[20] | 类型 u8 | 记录内偏移 i32 | 存储宽度 i16 | 声明宽度 i16 | 标志 i32 | 序号 i16`
类型：0 串 / 1 byte / 2 short / 3 int / 4 float / 5 double / 6 日期 / 7 时间

- 串：GBK、左对齐、不足补 `\0`；**容量 ≥ 汉字数×2 + 1**
- 数值：小端；`double` 用 8 字节
- 记录：`0x01` 打头，字段按描述符偏移稀疏布局

## 8. 注记样式速查

| 想要 | 参数 | 常用值 |
|---|---|---|
| 字号 | `h`/`w`（mm） | 大格号 2.0，点号 1.3 |
| 字距 | `gap` | 0.05–0.2 |
| 颜色 | `color` | 1=黑；其它看 colorlib |
| 旋转 | `angle` | 图廓注记常用 90 |
| 图层 | `layer` | 单独一层便于开关 |
| 位置 | 直接改 `x/y` | 锚点左下角，想居中就 `x-=字宽/2, y-=h/2` |

## 9. 配方

**① CSV → 点文件**
```python
import pandas as pd
df = pd.read_csv("pts.csv", dtype={"点号": str})      # dtype=str：别让 001 变成 1
pts = list(zip(df.X_mm, df.Y_mm))
rows = [(r.点号, float(r.X_mm), float(r.Y_mm)) for r in df.itertuples()]
write_wt("out.WT", pts,
         fields=[("点号","str",12), ("X_m","double",8), ("Y_m","double",8)],
         rows=rows, template="参考.WT", symbol=48)
```

**② 加字段 / 改值**：`wt_attrs.py set --where 字段=值 --set 字段=新值`（定长字节改写，不动几何）。

**③ 属性 → 注记**：读出属性 → 逐点生成 `items` → `write_wt_annot`。
点号放右上：`x+0.5, y-0.4`。

**④ 大格编号**：1 km 格网 → 每格中心放一个三位编号 → `write_wt_annot`。

**⑤ 改符号**：`set_symbol.py x.WT --symbol 48`（比重新生成安全，属性/注记不丢）。

**⑥ 读线做分析**：`read_wl` → 端点吸附/打断 → 图论（Strahler 分级、汇水面积）。

## 10. 生成后必做的校验

```python
pts, raw = read_wt("out.WT")
assert raw[:8] == b"WMAP`D22"                 # 魔数对（别拿 .WL 当模板！）
assert len(pts) == 期望点数
f, rows = read_wt_attrs("out.WT")
assert len(rows) == len(pts) + 1              # 首条空记录
assert rows[1]["点号"] == "001A1"             # 没串行
```

结构化自检直接跑 `scripts/demo_selftest.py`（含段长、文本池、框表断言）。

## 11. 文件清单

| 文件 | 作用 |
|---|---|
| `scripts/mapgis_wl.py` | 读写库：`read_wl/write_wl/read_wt/write_wt/read_wt_attrs/write_wt_annot/read_wt_annot` |
| `scripts/wt_attrs.py` | 属性导出 CSV / 按条件就地改值 |
| `scripts/set_symbol.py` | 只改子图号、高宽、颜色，其它字节不动 |
| `scripts/demo_selftest.py` | 5 项断言的端到端自检 |
| `reference/format.md` | 字节级结构表（比本文更细） |
| `reference/pitfalls.md` | 10 条实测坑与解法 |

## 12. 依赖与限制

- Python 3.9+，仅需 `numpy`（`pandas` 仅配方里用到）
- 坐标系：文件里只有投影/椭球索引，真正 CRS 依赖 `mapgis67\program\ellip.dat`；
  本库按"图面毫米"处理，1:50000 时 1 mm = 50 m
- 生成的文件已在 MAPGIS 6.7 里做过显示验收（点文件 + 注记，见 `docs/verification.md`）；
  线/面文件的**渲染**尚未逐项验收，只有结构自检；换机/Slib 版本后建议再开一眼
