---
name: mapgis-automation
description: "用 Win32 消息与键鼠注入自动化操作 MAPGIS 6.7 桌面端（W60_DTM 空间分析、mdiedit6x 输入编辑、mapout60 输出）。当需要无人值守地点击 MAPGIS 菜单/对话框、批量出图、或为 MAPGIS 编写自动化脚本与 MCP 服务时使用。"
---

# MAPGIS 6.7 桌面自动化

MAPGIS 6.7 是 VB6 程序，没有命令行接口，也没有可用的 COM 自动化。
可行的自动化路径只有一条：**Win32 窗口消息 + 键鼠注入 + 截图核对**。

详细踩坑与命令表见同目录 `references/`；通用驱动脚本见 `scripts/drv.ps1`。

## 三个基本动作

### 1. 找窗口

```powershell
# 按进程名找主窗口
$p = Get-Process W60_DTM | Sort-Object StartTime -Descending | Select-Object -First 1
$p.MainWindowHandle

# 按标题找对话框（比"最新窗口"可靠）
# EnumWindows + GetWindowThreadProcessId + GetWindowTextW
```

**不要用"取最新窗口"**：MAPGIS 里常年存在隐藏窗口（`错误警告`、`tooltips_class32`），会抢到错误句柄。

### 2. 发命令

菜单命令用 `WM_COMMAND`（0x0111）发给**主框架窗口**：

```powershell
PostMessage($hMain, 0x0111, [IntPtr]$cmdId, [IntPtr]::Zero)
```

命令 ID 可以用 `GetMenu` / `GetSubMenu` / `GetMenuItemID` 现场枚举，不用猜：

```powershell
# 例：枚举"光栅输出"子菜单
GetSubMenu(GetMenu($hMain), 2) → 逐项 GetMenuItemID / GetMenuStringW
```

常用 ID（W60_DTM / mdiedit6x）：

| ID | 功能 |
|---|---|
| 32946 | 平面等值线图绘制（DTM） |
| 32804 / 32805 / 32806 | 存点 / 线 / 区数据文件（DTM） |
| 57600 | 新建工程（编辑） |
| 32851 | 打开工程或文件 |
| 32771 | 页面设置（输出模式） |
| 32780 | 工程输出（编辑→输出模式） |
| 32791 | 返回编辑 |
| 32982 | **生成JPEG图像**（输出模式） |

### 3. 填对话框

```powershell
# 子控件按 id 找，再发消息
SendMessage($hDlg, 0x0111, 1, 0)          # 点确定（WM_COMMAND）
SendMessage($hEdit, 0x000C, 0, "值")      # WM_SETTEXT
SendMessage($hBtn, 0x00F5, 0, 0)          # BM_CLICK
SendMessage($hCombo, 0x014E, 1, 0)        # CB_SETCURSEL
```

先 `EnumChildWindows` 打印每个控件的 `id / class / rect / text`，再动手 —— 比看截图猜快得多。

## 三个必知的坑

1. **隐藏模态框会吞掉所有命令**
   `错误警告：MapGis多用户服务器工作不正常` 的 `IsWindowVisible` 为 false，但它挡在消息循环里，导致"工程输出"点了没反应。
   处理：枚举该进程全部顶层窗口（含不可见），找到 `#32770` 就 `postbtn:1` / `btn:1`。

2. **菜单位置每次不同**
   VB6 自绘弹窗（`#32768`）的坐标随当前选中项变化。
   处理：用 `GetMenuItemRect` 取菜单项矩形；或从控件的 `GetWindowRect` 实时换算格心；操作完必须读回状态确认。

3. **点击可能落在错误控件上，改坏数据**
   例如色盘没弹出时，点击会落到等值线层值列，把 `126.49` 改成 `60`。
   处理：每次点击前先确认目标窗口标题；点击后截图/读值校验。

## 基础循环

```
枚举窗口 → 发命令 → 等 1~3 s → 截图或 EnumChildWindows 核对 → 下一步
```

驱动脚本 `scripts/drv.ps1` 已封装常用动作，`-Steps` 用分号串联：

```
wins | dlg | findtitle:xxx | use:<hwnd> | cmd:<id> | dlgcmd:<id>
click:x,y | rclick:x,y | dclick:x,y（相对对话框）
set:<id>=<text> | setedit:<id>=<text> | btn:<id> | postbtn:<id> | combo:<id> | comboi:<id>,<idx>
rgb（读色盘颜色号与 RGB） | shot:<path> | shotmain:<path> | keys:<SendKeys> | probe:x,y | sleep:<ms>
```

## 边界

- 需要解锁屏幕：`SetCursorPos` / `mouse_event` 在 `LockApp` 运行时无效
- 每一步都依赖上一屏的像素；窗口被遮挡、分辨率变化、DPI 缩放都会打断
- 长任务建议每步落一张截图，便于回看失败点

## 往 MCP 方向走

见仓库 `docs/roadmap.md`：把"窗口/命令/对话框"抽象成 4~6 个工具（open_map、set_levels、set_colors、export_jpeg、screenshot），
底层仍是这套 Win32 调用，但对模型暴露成语义操作；进一步可用 MAPGIS SDK / 二次开发接口替代 GUI。
