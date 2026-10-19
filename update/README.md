# update 交接索引 — ai-content-labeling-checker

> 诊断日期：2026-10-19
> 诊断方边界：只读诊断；未改任何受版本控制文件、未改 GitHub 状态、未发版、未改依赖。
> 唯一写入：本 `update/` 目录。

## 一句话结论

**建议迭代，产品面健康。** 438 项测试双解释器全绿、三类基准全达标、退出码 0/1/2/3 齐备、报告五产物两次逐字节一致、发布 zip sha256 与冻结态验收都实过。要修的是工程门禁：Python 3.8 已 EOL 但仍被 `requires-python`/CI 矩阵/`test_guard_ci.py` 三处锁死；CI 从不安装 `report`（openpyxl）extra，XLSX 确定性测试每次 skip；CI 不构建 exe，发布物可复现性只在本地。

## 文件索引

| 文件 | 用途 |
|---|---|
| [00-诊断报告.md](00-诊断报告.md) | 现状基线、自述逐项实测、做得好的部分、缺陷 D1-D9、失效模式逐条结论 |
| [01-迭代路线.md](01-迭代路线.md) | 分批动作、每批门禁、各 CI job 期望收集数、范围边界、本仓库特有的坑 |
| [02-提示词-迭代对话.md](02-提示词-迭代对话.md) | 可直接复制到新对话的完整执行提示词 |
| `03-执行记录.md` | 由**执行方**新建；记录决策、每批命令/汇总行/退出码，状态「待复验」 |

## 需要用户拍板的决策

### D-1 最低 Python 版本

| 方案 | 内容 | 收益 | 代价 | 建议 |
|---|---|---|---|---|
| **A** | `requires-python >= 3.12`；CI 改 windows 3.12 + ubuntu 3.12；`gui = PySide6>=6.12,<7`；`pkg = pyinstaller>=6.22,<7` | 与实测环境一致（3.12 + Qt 6.12 + PyInstaller 6.22 全过）；去掉 3.8 的 modulegraph 风险 | 排除 3.9–3.11 源码用户 | **推荐** |
| B | `>= 3.11`；CI 加 3.11 | 多覆盖一个受支持版本（3.11 至 2027-10） | 多一个矩阵作业；本次未在 3.11 实测 | 可选 |
| C | 保持 `>= 3.8` | 不动 | 3.8 已 EOL（2024-10-07）；不推荐 | 不推荐 |

> 事实：3.8 EOL 2024-10-07；3.9 EOL 2025-10-31；3.10 EOL 2026-10-01；3.11 至 2027-10-31；3.12 至 2028-10-31。
> 无论选哪个，`tests/test_guard_ci.py:109-110` 的 3.8 断言必须同步改（合法规格变更）。

### D-2 PySide6 版本口径

| 方案 | 内容 | 收益 | 代价 | 建议 |
|---|---|---|---|---|
| **A** | `gui = ["PySide6>=6.12,<7"]` | 实测 6.12.0 下 438 passed；与"抬下限"一致；去掉无谓的 `<6.8` 上限 | 需要新装 Qt 6.12 验收 | **推荐** |
| B | 保持 `["PySide6>=6.6,<6.8"]`（3.9+） | 不动 GUI 依赖 | 上限无实测理由；被排除在 6.8+ 之外 | 可选 |
| C | `["PySide6==6.12.0"]` 精确 pin | 最可复现 | 失去补丁版自动升级 | 仅当用户要求完全锁死 |

> 实测：py3.12.10 + PySide6 6.12.0 + openpyxl → `438 passed in 33.29s`，退出 0。

### D-3 CI 覆盖补齐范围

| 方案 | 内容 | 收益 | 代价 | 建议 |
|---|---|---|---|---|
| **A** | test job 加 `report` extra（XLSX 测试真跑）+ 每类 pytest job 加收集数对账 + 新增 windows/py3.12 的 `package` job（build_exe + verify_package） | 消除"永远 skip"与"发布物只在本地构建"两个缺口 | CI 时长 +1 个 build job（约 1 分钟量级） | **推荐** |
| B | 只加 `report` extra，不做 package job | 改动最小；XLSX 有覆盖 | exe 仍无 CI 门禁 | 可选 |
| C | 只做 package job，不加 report | 发布物有门禁 | XLSX 仍永远 skip | 不推荐 |

> 实测：dev-only（模拟当前 test job）`422 collected / 421 passed / 2 skipped`；全环境 `438 passed`。XLSX 测试（`test_report.py:217`）在 CI 无任何 job 安装 openpyxl → 永远 skip。

### D-4 版本与发布

| 方案 | 内容 | 收益 | 代价 | 建议 |
|---|---|---|---|---|
| **A** | 升 `0.1.1`（bugfix），本地构建 + 验证；**经用户确认后**发布新 Release | 与"门禁现代化 + 文档修正"对应；semver 清晰 | 需要用户打 tag/发 Release | **推荐** |
| B | 保持 0.1.0，只改 CI/本地，不发布 | 不涉及发布 | 用户拿到的 0.1.0 仍是旧文档/旧门禁（功能无差） | 可选 |
| C | 升 `0.2.0` 并加新功能 | 大版本叙事 | 本轮定位是工程加固，混新功能放大验证面 | 不推荐 |

> 不要移动 tag `v0.1.0`；发布新版本时新建 tag。

## 本次迭代的边界

- **做**：Python/Qt/PyInstaller 口径现代化；CI 去 3.8、加 report、加收集数对账、加 package job；README/交接文档 exe 体积与基准耗时修正；元数据（Alpha/actions/next_review）。
- **不做**：改规则库条目与 status 分布、改引擎判定/分级、改三类基准阈值、改真值 fixtures、改退出码、改打包白名单、引入联网通路、发布（除非 D-4 选发布且用户执行）。
- **并行任务**：如果另一个对话在改别的仓库，本仓库只动本目录；不要跨仓库 `git add -A`。

## 起点基线（执行方不要重新论证）

- 路径：`D:\ProgramData\zcode\10-13-ai-content-labeling-checker`
- HEAD：`b8a1a0547f993735e2ff6dfa48dfdb8d230d0bbd`；tag `v0.1.0`；与 `origin/main` 0/0；工作树干净。
- 测试：收集 **438**；py3.8 **438 passed**；py3.12 **438 passed**；dev-only **422 collected / 421 passed / 2 skipped**；py3.12 + PySide6 6.12.0 **438 passed**。
- 基准：`fields 30/30`、`constructed 23/23 检出 + 0/11 误报`、`diff 2/2`；退出 0；进程内 ≈0.19 s（README 写 0.12 s）。
- 退出码：合规 0 / 不合规 1 / 用法错 2 / 环境错 3；`bench` 0。
- 规则库：GB 45438-2025 25 条全 verified；办法 9 条（2 verified + 7 pending）；合计 27 verified / 7 pending。
- Release：CLI zip 7,401,819 B sha256 `604df863…c29e`；GUI zip 45,767,613 B sha256 `72fd7ab1…2e86c`；`verify_package.py --dist` 退出 0。
- 发布物体积：CLI 文件夹 17 MB / GUI 112 MB（README 写 ≈13 MB / ≈158 MB）。
- CI：最新 run `38387204924` 8 job 全 success；actions v4/v5 已收 Node20 弃用警告。
- 实测现代化路径：py3.12 + PyInstaller 6.22.3 + PySide6 6.12.0 → `build_exe --clean` + `verify_dist` 全过。