# mapgis-automation

让 AI / 脚本操作 **MAPGIS 6.7** 桌面端的实验性工具集与路线图。

MAPGIS 6.7 没有命令行、没有可用的 COM 接口，所有操作都得点菜单、填对话框。
本项目把这类操作沉淀成可复用的驱动脚本，并朝 **MCP server**（让模型直接调用 `open_grid` / `set_levels` / `export_jpeg` 这类语义工具）演进。

> 状态：实验性。已在 Windows 10 + MAPGIS 6.7 上跑通"网格化 → 等值线 → 白底分级配色 → 图层保存 → 工程输出 → 300 dpi JPEG"全流程，并用它批量出过 6 张地球化学异常图。

## 里面有什么

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 给 AI agent 用的技能说明（何时用、三个基本动作、三个坑、动作语法） |
| `scripts/drv.ps1` | 通用驱动：按进程名定位，`-Steps` 分号串联动作 |
| `docs/win32-notes.md` | 窗口 / 控件 id / 菜单命令 id 速查（实测） |
| `docs/roadmap.md` | 从脚本到 MCP 的分阶段路线 |

## 快速开始

```powershell
# 列出目标进程的可见窗口
.\scripts\drv.ps1 -Proc W60_DTM -Steps "wins"

# 发菜单命令（平面等值线图绘制）
.\scripts\drv.ps1 -Proc W60_DTM -Steps "cmd:32946;sleep:3500;wins"

# 填对话框、点确定、截图核对
.\scripts\drv.ps1 -Proc mdiedit6x -Steps "findtitle:设置输出位图的分辨率;setedit:1005=300;postbtn:1;sleep:45000"

# 输出模式生成 JPEG
.\scripts\drv.ps1 -Proc mdiedit6x -Steps "bring;cmd:32982;sleep:5000;wins"
```

动作一览：

```
wins | dlg | findtitle:<子串> | use:<hwnd> | cmd:<id> | dlgcmd:<id>
click:x,y | rclick:x,y | dclick:x,y（相对对话框）
set:<id>=<文本> | setedit:<id>=<文本> | btn:<id> | postbtn:<id>
combo:<id> | comboi:<id>,<序号> | chk:<id> | listitems:<id>
rgb（色盘颜色号 + RGB） | colnum | shot:<png> | shotmain:<png>
keys:<SendKeys> | probe:x,y | sleep:<ms>
```

## 三个必须知道的坑

1. **隐藏模态框**：`错误警告（MapGis多用户服务器工作不正常）` 的 `IsWindowVisible=false`，但会吞掉后续所有命令，表现为"点了没反应"。要先枚举不可见窗口并点掉它。
2. **坐标漂移**：VB6 自绘弹窗（`#32768`）每次打开位置/滚动位置都不同，固定坐标必然出错。用 `GetMenuItemRect` / 控件 `GetWindowRect` 实时换算，操作后读回校验。
3. **误伤数据**：点击落到错误控件会改坏参数（例如把等值线层值 `126.49` 改成 `60`）。每次点击前确认窗口标题，点击后截图核对。

## 路线图（摘要）

1. 脚本化（当前）：Win32 消息 + 键鼠注入
2. 抽象层：把动作封装为模块 / Python `ctypes` 库
3. **MCP server**：暴露 `open_grid`、`set_levels`、`set_band_colors`、`save_layers`、`export_jpeg`、`screenshot`
4. 稳定化：模板匹配 / OCR 替代固定坐标，状态机 + 重试
5. 绕开 GUI：直接读 `.GRD` / `.WT/.WL/.WP`，或用 MX 二次开发接口
6. 终局：MAPGIS 只做网格化，成图交给 GDAL / QGIS / Matplotlib

详见 [`docs/roadmap.md`](docs/roadmap.md)。

## 环境

- Windows 10/11，MAPGIS 6.7（`C:\mapgis67\program\`）
- 加密狗服务 `DogServer67.exe` 需先启动
- 运行期间**屏幕必须解锁**（`LockApp` 存在时键鼠注入无效）

## License

MIT
