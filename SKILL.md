---
name: mapgis-automation
description: "MAPGIS 6.7 自动化的总入口：先判断任务该走「文件级」（纯 Python 读写 .WT/.WL/.WP，不启动软件）还是「界面级」（Win32 消息驱动菜单），再转到对应技能。当用户要求批量生成/修改 MAPGIS 点线面数据、挂属性、出图，或自动化操作 MAPGIS 6.7 时，先读本文件做路线选择。"
---

# MAPGIS 6.7 自动化总入口

> 仓库：https://github.com/ZhuYiXuanNB/mapgis-automation
> 本文件只负责**路线判定 + 界面级基础能力**；数据操作细节都在子技能里。

## 0. 先选路线：90% 的坑源于选错路线

| 你要做的事 | 走哪条路 | 去哪儿 |
|---|---|---|
| 生成/修改 `.WT` `.WL` `.WP`、挂属性、改符号 | **文件级**（不启动 MAPGIS） | [`skills/mapgis-native-file/SKILL.md`](skills/mapgis-native-file/SKILL.md) |
| 属性 → 注记（点号、大格编号）、生成格网线 | **文件级** | 同上（`make_grid_labels` 思路在 SKILL 配方里） |
| Excel 采样数据 → 单元素/综合异常图（要网格化、等值线、工程输出） | **混合**：文件级备数据 + 界面级出图 | [`skills/geochemical-anomaly/SKILL.md`](skills/geochemical-anomaly/SKILL.md) |
| 必须用 MAPGIS 内部算法（网格化 DTM、空间分析、图幅裁剪） | **界面级** | 本文 §2 + `scripts/drv.ps1` |
| 只想看看文件对不对/读出坐标 | **文件级** | [`skills/mapgis-native-file/SKILL.md`](skills/mapgis-native-file/SKILL.md) |

**判定口诀：能自己算出结果 → 文件级；必须让 MAPGIS 算 → 界面级。**

> 旧版本说"MAPGIS 没有命令行，自动化只有 Win32 一条路"——**这句话已过时**。
> 自 2026-11 起，点/线/面的二进制结构已摸清（`skills/mapgis-native-file/references/format.md`），
> 常规数据准备可以完全不碰界面，只在**最终目视确认**和**内部算法**时才回到桌面端。

## 1. 路线 A：文件级（先试这条）

```bash
python skills/mapgis-native-file/scripts/mapgis_native.py verify x.WT   # 三判据自检
python skills/mapgis-native-file/scripts/wt_attrs.py dump --wt x.WT --out attrs.csv
```

关键约束（详见 mapgis-native-file 技能）：

- 文件头（657 B）与附属段**从真实文件克隆**，不要凭空造；
- 点文件 5 段、线文件 8 段，缺任一段 → 能读不能显示（已实测：补齐后 MAPGIS 正常显示，
  见 [`docs/verification.md`](docs/verification.md)）；
- 改完文件在 MAPGIS 里必须「移除图层 → 重新添加 → 复位窗口」，否则看到的是缓存。

**什么时候别用文件级**：需要 MAPGIS 自己的拓扑重构、构区、等值线追踪——这些算法在本仓库没有实现。

## 2. 路线 B：界面级（Win32 消息 + 键鼠注入）

MAPGIS 6.7 是 VB6 程序，没有命令行接口，也没有可用 COM。能自动化的只有窗口消息：

```powershell
# 列出进程的可见窗口
.\scripts\drv.ps1 -Proc W60_DTM -Steps "wins"

# 发菜单命令（例：平面等值线图绘制）
.\scripts\drv.ps1 -Proc W60_DTM -Steps "cmd:32946;sleep:3500;wins"

# 填对话框 + 确定 + 截图核对
.\scripts\drv.ps1 -Proc mdiedit6x -Steps "findtitle:设置输出位图的分辨率;setedit:1005=300;postbtn:1"
```

| 项 | 位置 |
|---|---|
| 主程序 | `C:\mapgis67\program\`：`mdiedit6x.exe` 编辑、`W60_DTM.exe` DTM、`W60_Anly.exe` 空间分析、`mapout60.exe` 输出 |
| 加密狗服务 | `DogServer67.exe`（须先启动） |
| 系统库 | `C:\mapgis67\Slib`、`Slib5000`、`SuvSlib` |
| 工作目录 | 短英文路径，如 `C:\ws`（中文长路径支持差） |

### 2.1 三个基本动作

1. **找窗口**：按进程名 + 标题找，**不要用"最新窗口"**（隐藏的 `错误警告`/`tooltips` 会抢句柄）。
2. **发命令**：`PostMessage(hMain, 0x0111, cmdId, 0)`；命令 ID 用 `GetMenu`/`GetMenuItemID` 现场枚举。
3. **填对话框**：`EnumChildWindows` 打印 `id/class/rect/text` 再动手；`WM_SETTEXT`/`BM_CLICK`/`CB_SETCURSEL`。

动作语法（`-Steps` 用分号串联）：

```
wins | dlg | findtitle:<子串> | use:<hwnd> | cmd:<id> | dlgcmd:<id>
click:x,y | rclick:x,y | dclick:x,y（相对对话框）
set:<id>=<文本> | setedit:<id>=<文本> | btn:<id> | postbtn:<id>
combo:<id> | comboi:<id>,<序号> | chk:<id> | listitems:<id>
rgb | colnum | shot:<png> | shotmain:<png> | keys:<SendKeys> | probe:x,y | sleep:<ms>
```

菜单命令 ID / 控件 ID 速查：[docs/win32-notes.md](docs/win32-notes.md)。

### 2.2 必知的坑

1. **隐藏模态框吞命令**：`错误警告（MapGis多用户服务器工作不正常）` 的 `IsWindowVisible=false`，但挡在消息循环里。
   → 枚举该进程**全部**顶层窗口（含不可见），遇到 `#32770` 就点掉。
2. **菜单坐标每次不同**：VB6 自绘弹窗 `#32768` 位置随滚动变化。
   → 用 `GetMenuItemRect`/`GetWindowRect` 实时换算，点完读回校验。
3. **点错控件会改坏数据**：例如色盘没弹出时点到层值列，把 `126.49` 改成 `60`。
   → 点前确认窗口标题，点后截图/读值核对。

其余 20+ 条见 `skills/geochemical-anomaly/pitfalls.md`。

## 3. 两条路怎么衔接（标准工作流）

```
Excel 采样表
   │  ① 文件级：生成 .WT（坐标+属性）      → skills/mapgis-native-file
   ▼
MAPGIS 编辑：添加文件 → 目视确认符号/注记  → 本技能 §2（可选，也可以人工确认）
   │  ② 界面级：DTM 网格化 → 等值线 → 分级配色
   ▼
工程输出 JPG                             → 本技能 §2 / drv.ps1
```

**缓存提醒**：外部改过 `.WT` 后，MAPGIS 不会自动刷新——必须「移除图层 → 重新添加 → 复位窗口」。

## 4. 常见任务索引

| 任务 | 入口 |
|---|---|
| CSV → 点文件 / 改属性 / 改符号 | `skills/mapgis-native-file` §9 配方 ①②⑤ |
| 属性 → 注记（点号） | `skills/mapgis-native-file` §4.3 + 配方 ③ |
| 大格编号 / 格网线 | `skills/mapgis-native-file` 配方 ④⑥ |
| 读水系做分级/拓扑 | `skills/mapgis-native-file` 配方 ⑥ |
| 网格化、等值线、异常分带 | `skills/geochemical-anomaly/SKILL.md` |
| 出 JPG、改分辨率 | 本技能 §2 命令 ID `32982` / `32946` |

## 5. 环境

- Windows 10/11 + MAPGIS 6.7（`C:\mapgis67\program\`）
- 界面级：加密狗服务先启动，**屏幕必须解锁**
- 文件级：Python 3.9+（纯标准库，无第三方依赖）

## 6. 维护约定

- 新知识写进**对应子技能**的 `reference/`，不要都堆在根目录；
- 改文件格式结论时，同步 `skills/mapgis-native-file/references/format.md` 与 `docs/binary-format.md`；
- 提交前跑一遍 `python skills/mapgis-native-file/scripts/selftest.py`（需真实样本；缺样本会 SKIP，不算通过）。
