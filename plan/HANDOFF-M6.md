# HANDOFF-M6：M5 → M6 交接快照

> **用法**：新对话读 `plan/HANDOFF-M6.md` 继续完成任务（会话启动命令给绝对路径即可）。
> **上一棒**：M5 桌面交付（`gui/` + `packaging/` + 双 exe + 演示素材 + 技术报告）✅ 完成 2026-10-13。
> **下一棒**：M6 发布——脱敏 + GitHub Release（挂 exe）+ 收尾固化。

---

## 一、M5 交付物（已落地，勿重复造）

**桌面界面**：`src/labelcheck/gui/`

| 模块 | 职责 |
|---|---|
| `services.py` | **唯一引擎调用点**，**零 Qt、零判定**：`check_single` / `scan_batch` / `load_baseline` / `export_report` / `run_bench` / `rules_overview` / `scenario_options` |
| `format.py` | 引擎对象 → 展示行/文本（零判定；等级中文名复用 `report.GRADE_LABELS`） |
| `tabs.py` | 六页签（单件核验 / 批量扫描 / 两轮对账 / 基准指标 / 规则库与依据 / 关于）；函数体内 `_qt()` 惰性取 Qt 符号 |
| `main_window.py` | 主窗口装配 + 数据目录下发；**顶层 import PySide6** |

**打包支持**：`src/labelcheck/packaging/`

| 函数 | 职责 |
|---|---|
| `build_datas(data_dir, root)` | PyInstaller `datas` 白名单（`rules`/`mapping`/`truth`/`parse`/`samples`/`knowledge`） |
| `assert_ready(data_dir)` | 构建前置检查（白名单齐全 + 哨兵文件），缺则抛 `EnvironmentError_` |
| `verify_dist(dist_dir, exe_name, run, gui_selftest)` | **构建后验伪**：数据目录必须**落在 dist 之内** + 冻结态标记 + 生效规则数 > 0 |
| `neutral_env(env)` | 中立环境（去 `LABELCHECK_DATA_DIR`） |
| `DATA_SUBDIRS` / `GUI_EXE_NAME` / `CLI_EXE_NAME` / `GUI_SELFTEST_FLAG` | 单一白名单与产物名 |

**CLI**：新增 `gui` 子命令（`--check` 做可加载性自检）；**函数体内惰性导入** PySide6，
缺 extra → exit 3。

**工具**：`tools/build_exe.py`、`tools/labelcheck.spec`、`tools/entry_gui.py`（支持
`--selftest <file>`）、`tools/entry_cli.py`、`tools/verify_package.py`、`tools/make_demo_assets.py`。

**文档**：`docs/技术报告.md`（七章）、`docs/demo/`（5 张页签截图 + `demo.gif`）。

**实测产物**：`dist/labelcheck-gui/labelcheck-gui.exe`（`console=False`，文件夹 **112 MB**）+
`dist/labelcheck/labelcheck.exe`（`console=True`，文件夹 **17 MB**，**不含 Qt、含 openpyxl**）。
> 体积口径（2026-10-19 按 Release v0.1.0 附件实测修正）：CLI 文件夹 17 MB / GUI 文件夹 112 MB；
> zip 分别 7,401,819 B / 45,767,613 B。旧值 ≈14/≈158 MB 为估测，已作废（见 plan/06 D45）。
> **v0.2.0 本机构建另有口径**：py3.12 + PySide6 6.12 + PyInstaller 6.22 → CLI 19 MB / GUI 120 MB
> （体积随 Qt/PyInstaller 版本变化，故对外一律以"你下载到的 Release 附件"为准）。

## 二、M5 关键口径（**与本 HANDOFF 同步的既定口径，改前先对照**）

| 变化 | 内容 | 影响面 |
|---|---|---|
| **GUI 零判定**（D36） | 判定/分级/分派只在引擎；`gui/services.py` 只调引擎入口，AST 守门断言其不 import 判定器、不 import PySide6 | `gui/`/守门 |
| **服务层零 Qt** | `services.py`/`format.py` 无 PySide6（含函数体内）→ 无 GUI 环境也能导入，故用普通 pytest 全覆盖 | GUI/测试 |
| **惰性导入纪律** | `cli/` 顶层禁 GUI；`gui` 子命令函数体内导入；`tabs.py` 函数体内 `_qt()` | CLI/GUI |
| **打包数据白名单**（D37） | 只内嵌 `DATA_SUBDIRS`，**不**整仓塞 `data/`（私有件/报告输出不入包） | 打包 |
| **冻结态验伪**（D38） | 数据目录必须**落在 dist 之内**；中立环境（清 `LABELCHECK_DATA_DIR`、以 exe 目录为 CWD）实跑 | 打包/验收 |
| **双 exe 分工**（D39） | GUI `console=False`；CLI `console=True` 且排除 Qt（保留 openpyxl，XLSX 是文档化功能） | spec/构建 |
| **素材离屏渲染**（D40） | `tools/make_demo_assets.py` 离屏渲染真实控件；**不做位级守门**（字体渲染跨机器不同） | 演示/README |
| **冻结态提示口径** | `report` 的 XLSX 缺失提示按 `is_frozen()` 分流：冻结态说"本发行包未内嵌 XLSX 导出"，**不**叫用户 `pip install` | `report/` |

## 三、M6 待办（下一棒）——**发布门**

> **M6 执行后状态（2026-10-13 回写）**：1️⃣ 脱敏脚本 ✅ 已实现（`tools/audit_desensitize.py`，
> 四步 + 产物本体扫描 + 阳性/阴性对照自检）；2️⃣ 历史邮箱重写 ✅ **已执行**（用户授权后
> `filter-branch --env-filter` 全历史改写为 noreply；二次 `tree-filter` 清"留档自命中"；验证 0 残留）；
> 3️⃣ exe/dist 不入仓 ✅ 已确认；4️⃣ GitHub Release ✅ **已发布**（仓库 `yuluo554/ai-content-labeling-checker`
> 公开 + Release **v0.1.0** 挂双 exe 的 ASCII 命名 zip；CI 8 job 全绿；发布物下载核 sha256 + 冻结态自检）；
> 5️⃣ 收尾固化 ✅ 已完成。
> **动作留档**：[RELEASE-M6.md](RELEASE-M6.md)（脱敏审计结果 + 发布时序 + **首跑 CI 抓出的 3 处真实缺陷**
> + 二次历史重写瑕疵留痕）。

1. **脱敏四步审计**（`tools/audit_desensitize.py`，M6 新建）——✅ **已实现**：
   - **提交元数据邮箱**：`git log --format="%ae %ce"` 是**真实个人邮箱**（实测 5 条提交）→ 发布前用
     `filter-branch --env-filter`（或 `git-filter-repo`）全历史改写为 GitHub noreply，
     并同步 `git config user.email`。**历史重写属对外结构性动作，须用户明确授权**后再做。⬜ 待授权
   - **已知假阳性**：示例标识卡里的假 sha256 hex 串（64 连续 hex）会命中"18 位身份证"正则 →
     phone/idcard 模式已加 **hex 边界环视** `(?<![0-9a-fA-F])…(?![0-9a-fA-F])`，
     并把该形态写进 `--selftest` 阴性对照。✅
   - **`data/parse/fixtures.json` 白名单**：内含 base64 的构造容器（非真实媒体），
     已列白名单，并确认 `.gitattributes` 已当文本。✅
   - **`data/knowledge/raw/` 版权口径**：办法全文为行政公文（可留档）；国标**不转载全文**，
     只留书目元数据 + 条号要点对照（已按此办理，M6 已复核）。✅
   - `data/**/_private/` 已在 `.gitignore`（M0 补齐），M6 已复核。✅
2. **M3/M4/M5 新增文件不得带真实路径/主机名**：报告 `root` 字段写的是用户传入路径
   （本机为 `D:\ProgramData\...`）——报告产物不入仓；M6 已确认 `.gitignore` 已排除常见报告
   输出目录（`build-*/`、`scan-out*/` 等，已在）。另发现并修正 `plan/HANDOFF-M1.md` 环境坑行的
   真实用户目录路径（改为描述性指代）。✅
3. **exe/dist 产物不入仓**：`dist/`、`build/` 已在 `.gitignore`；`tools/*.spec` **例外放行**
   （构建脚本入仓）。M6 已确认 `git ls-files` 无 `dist/`/`build/` 文件。Release **只挂 exe**
   （`dist/*` 打包成 zip）。✅
4. **GitHub Release**：`labelcheck-gui.exe` + `labelcheck.exe`（onedir zip）——✅ **已发布**
   Release **v0.1.0**（`https://github.com/yuluo554/ai-content-labeling-checker/releases/tag/v0.1.0`，
   附件 ASCII 命名：`labelcheck-cli/gui-v0.1.0-win64.zip`）。演示素材随仓库（`docs/demo/`）。
5. **收尾固化**：README 状态行/链接核对 ✅；`plan/05` M6 DoD 勾选 ✅；`plan/00` 状态回写 ✅；
   `plan/06` D41–D43 + P3 结论 ✅；`tools/README.md` 登记 ✅；`git tag v0.1.0` + `gh release create` ✅。

## 四、关键命令速查

```bash
# 桌面界面（需 gui extra）
python -m pip install -e ".[gui]"
PYTHONPATH=src py -X utf8 -m labelcheck gui
QT_QPA_PLATFORM=offscreen PYTHONPATH=src py -X utf8 -m labelcheck gui --check   # 无显示环境冒烟

# 打包（需 pkg extra）——构建 + 自动校验
py -3.12 -X utf8 tools/build_exe.py --clean
py -3.12 -X utf8 tools/verify_package.py          # 中立环境验收（清环境变量）
py -3.12 -X utf8 tools/verify_package.py --json

# 演示素材（需 gui extra；离屏渲染）
py -3.12 -X utf8 tools/make_demo_assets.py
py -3.12 -X utf8 tools/make_demo_assets.py --check

# 内置基准（仓库真实数据下必须全部达标 → exit 0）
PYTHONPATH=src py -X utf8 -m labelcheck bench
PYTHONPATH=src py -X utf8 -m labelcheck bench --json

# 生成器（改数据唯一路径；--check 断言位级一致）——共 4 个
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py && py -X utf8 tools/gen_mapping.py \
  && py -X utf8 tools/gen_samples.py && py -X utf8 tools/gen_parse.py
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_parse.py --check

# 数据与自检
PYTHONPATH=src py -X utf8 -m labelcheck selfcheck
PYTHONPATH=src py -X utf8 -m labelcheck version

# 测试（两版本）
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -X utf8 -m pytest tests/ -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest tests/ -q
```

## 五、本机环境事实与坑（沿用 M0–M5，仅列实测）

- 解释器：`py -0p` → **3.12**（3.8.8 仍在机器上但已 EOL，v0.2.0 起不再支持）；Windows 上 `python`
  是商店占位符，**一律用 `py`**；命令加 `-X utf8`。**Git Bash 里 `python - <<'PY'`（heredoc）在本机是商店占位符**，用 `py -X utf8 -`。
- **PySide6 6.12.0**、**PyInstaller 6.22.3**、openpyxl 3.1.5（三者同一 py3.12 环境，v0.2.0 实测）。
  旧 M5 口径（3.8 装 6.6.3.1 / PyInstaller 5.13.2、openpyxl 与 Pillow 仅 3.8）已作废。
  **PyInstaller 5/6 的 PYZ 写法差异**：用 `PYZ(analysis.pure)`（两版都接受；6 已移除 `zipped_data`）。
- **离屏 Qt**：`QT_QPA_PLATFORM=offscreen`；会打印 `QFontDatabase: Cannot find font directory`
  与 `This plugin does not support propagateSizeHints()`——**无害**，不是失败。
- **构建前必须杀掉残留的 `labelcheck-gui.exe`**：否则 `dist/` 里的 `base_library.zip` 被占用，
  `--clean` 会 `PermissionError`（我踩过一次）。`taskkill //F //IM labelcheck-gui.exe`。
- **冻结态验伪不能"验了个寂寞"**：`dist/` 在仓库树内，若内嵌数据缺失，冻结态会**兜底命中
  仓库 `data/`**（我实测过：删掉 `dist/labelcheck/data` 后 exe 仍能跑，读的是仓库数据）。
  `verify_dist` 靠**先做静态路径断言**（`dist/**/data/rules/registry.json` 必须存在）
  再实跑，故能拦住——**改这个顺序会破功**。
- **`data/**` 必须零 CR**：二进制不要直接落仓（会命中 EOL 门）——用 base64。
- **零政策字面量门会扫 `gui/` 之外的源码**：`test_guard_data.py` 的 `test_policy_tokens_absent_from_engine_sources`
  **跳过 `gui/`**，但**不跳过** `packaging/` 与 `tools/`——写注释时别出现政策键名。
- 全项目测试**单次约 8 秒**（含 GUI offscreen + 打包）；跨平台结论**以 CI 为准，别拿本机全绿当证据**。

## 六、M5 DoD 逐项核对（已闭合）

- [x] **PySide6 界面（FR-12）**：六页签；GUI 只渲染引擎结果、零判定逻辑（AST 守门锁死）
- [x] **依赖走 optional extra**：`gui = ["PySide6>=6.12,<7"]`（v0.2.0 口径；M5 当时为 `["PySide6"]`）；
      本机 py3.12 实测 6.12.0；GUI 测试 `pytest.importorskip("PySide6")` 声明式跳过
- [x] **PyInstaller onedir 双 exe**：GUI（`console=False`）+ CLI（`console=True`）；
      CLI 排除 Qt（文件夹 17 MB）/ GUI 含 Qt（文件夹 112 MB）
- [x] **数据白名单内嵌 + 构建后校验**：`build_datas()` 白名单；`verify_dist()` 断言数据目录
      **落在 dist 之内**；中立环境实跑——**实测双 exe 均通过**（`frozen=True`、规则 27 条）
- [x] **演示素材**：`tools/make_demo_assets.py` 离屏渲染 `docs/demo/`（截图 + GIF），进 README
- [x] **技术报告**：`docs/技术报告.md`（标识规则化 / 元数据映射 / 批量与证据链 / 基准指标 /
      交付形态 / 守门 / 已知边界）
- [x] **plan 回写**：`plan/04 §十二` 新增 GUI/打包章节 + §十守门表 + §十一接口清单；
      `plan/03` 模块表与 §九状态；`plan/05` M5 DoD；`plan/06` D36–D40；`plan/00` 回写
- [x] **测试全绿（420 项，M5 当时口径）**：3.8 通过 420；3.12 通过 419 + 1 skip（XLSX 确定性需 openpyxl）；
      GUI 服务层 19 + 分层守门 7 + 页签 offscreen 23 + 打包 18（含 2 项真 exe 实跑）
      > **v0.2.0 现状（2026-10-19）**：全量 **463 项**、py3.12 单一解释器全通过、CI 各 job 均装 `report`
      > extra 故 XLSX 用例真跑（不再有"永远 skip"）。见 `update/03-执行记录.md`。
- [x] 生成器 4 个 `--check` 位级一致；`selfcheck` 生效 27 条；`bench` 三类全达标
- [x] CI 新增 `gui-smoke`（windows/py3.12 + offscreen）与 `packaging-guard`（windows3.8 +
      ubuntu3.12，core-only 零 PyInstaller）两个 job；4 job 全过 YAML 守门
      > **v0.2.0 现状（2026-10-19）**：CI 扩为 5 类 8 job（test×2 / cli-smoke×2 / gui-smoke /
      > packaging-guard×2 / **package**），全 py3.12；含每 job 收集数对账与真 exe 构建验收。

**偏差说明**：

1. **CLI exe 保留 openpyxl**（初版排除）：排除后 `report.xlsx` 静默降级成 CSV，而冻结态用户
   **装不上** openpyxl（`pip install` 提示在冻结态是错的）——这是"文档化功能在发行包里不可用"，
   故改为**保留 openpyxl、只排除 Qt**（体积仅 13→14 MB）。同时把 `report` 的降级提示改成
   `is_frozen()` 分流（冻结态说"本发行包未内嵌 XLSX 导出"）。
2. **GUI exe 用 `--selftest <file>` 而非 stdout**：窗口版（`console=False`）stdout 不接终端，
   故 `entry_gui.py` 支持把自检结果写 JSON 文件——`verify_dist(gui_selftest=True)` 据此验收。
3. **`range` check_type 仍未覆盖**（沿用 M4）：生效规则库中不存在该类规则 → `fields` 基准在
   `notes` 里如实说明。若 M6 建了 `range` 规则，基准自动开始覆盖。

## 七、M5 未做 / 留给 M6 的明确边界

1. **脱敏脚本尚未实现**（`tools/audit_desensitize.py` 仍是 ⬜）——M6 第一件事。
2. **历史邮箱重写未做**（需用户授权）——见 §三.1。
3. **Release 未创建**（本机未推送/未打 tag）——M6 做。
4. **演示 GIF 只有一张**（页签轮播）——如需更细的分步演示，M6 可扩 `make_demo_assets.py`。
