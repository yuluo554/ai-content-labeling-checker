# 10-13-ai-content-labeling-checker 项目计划总览

**项目**：AI 生成合成内容标识合规核查器（内容合规工具，Windows 桌面 + CLI 双形态，显式/隐式标识核验 + 元数据字段映射 + 批量扫描 + 证据链）
**方法论**：ai-tool-project-sprint（条款库 + 版本化核查规则库 + 合成样本真值基准 + 证据指纹 + 离线交付）
**项目系列**：①建造（已发布）②电力 ③医疗 ④招投标 ⑤食品 ⑥发票 ⑦简历 ⑧结构加固 ⑨钢结构 ⑩脚手架 → ⑪文献审计工作台 → ⑫个税计算器 → ⑬温室气体核算工作台 → ⑭个保合规审计工作台 → **⑮本项目**
**命名约定**：本地目录 `10-13-ai-content-labeling-checker`（`10-13`=2026-10-13 日期标签）；**GitHub 仓库名 = `ai-content-labeling-checker`（纯净名，去日期前缀）**，沿用系列惯例 `yuluo554/<kebab-name>`；署名 `yuluo554`（LICENSE/pyproject 一致）。
**定位宣言（v1）**：把"显式标识 + 隐式元数据标识"的合规核验做成**规则化、可批量、留指纹证据**的本地工具——LLM 聊天给不了持久规则库、逐字段核验与全量批处理对账，本工具是内容标识合规的核查防线（且明确站在合规侧，绝不做标识规避）。

## 文档索引

| 文档 | 内容 | 状态 |
|---|---|---|
| [01-题目详细定义.md](01-题目详细定义.md) | 项目题全文 v1（介绍/任务/材料/评分/锚点/边界） | ✅ v1 定稿 2026-10-13 |
| [02-需求解读.md](02-需求解读.md) | 痛点→能力转译、FR 清单带优先级、NFR、边界守卫 | ✅ M0 定稿 |
| [03-架构与技术选型.md](03-架构与技术选型.md) | 分层架构、解析器选型、零依赖核心层、目录布局 | ✅ M0 定稿 |
| [04-模块详设.md](04-模块详设.md) | 规则库 schema、字段映射模型、批量对账算法、报告模板、退出码、确定性守门 | ✅ M0 定稿 |
| [05-数据计划与里程碑.md](05-数据计划与里程碑.md) | 规则库入库策略、合成样本生成器、M0–M6 DoD | ✅ M0 定稿 |
| [06-决策记录.md](06-决策记录.md) | 重大决策表 + 待核对项 + 缓议项 + 弃选项 | ✅ M0 定稿；M1 回写 V1–V5；M2 回写 D22–D27 + P1/P2 结论；M3 回写 D28–D32；M4 回写 D33–D35；M5 回写 D36–D40；**M6 回写 D41–D43 + P3 结论** |
| [HANDOFF-M1.md](HANDOFF-M1.md) | M0→M1 交接快照（进度/待办/既定口径/环境坑/DoD/速查） | ✅ M0 收尾 |
| [HANDOFF-M2.md](HANDOFF-M2.md) | M1→M2 交接快照 | ✅ M1 收尾 |
| [HANDOFF-M3.md](HANDOFF-M3.md) | M2→M3 交接快照 | ✅ M2 收尾 |
| [HANDOFF-M4.md](HANDOFF-M4.md) | M3→M4 交接快照 | ✅ M3 收尾 |
| [HANDOFF-M5.md](HANDOFF-M5.md) | M4→M5 交接快照 | ✅ M4 收尾 |
| [HANDOFF-M6.md](HANDOFF-M6.md) | M5→M6 交接快照（M6 执行后状态就地回写） | ✅ M5 收尾；M6 回写待办区 |
| [RELEASE-M6.md](RELEASE-M6.md) | M6 发布留档（脱敏审计结果 / 发布动作时序；发布动作待用户授权） | ✅ 骨架已落（授权后回填） |

## 决策记录（摘要，全文见 [06](06-决策记录.md)）

| 日期 | 决策 | 结论 |
|---|---|---|
| 2026-10-13 | 选题 | 系列第 15 题（不参赛，发 GitHub）：AI 生成合成内容标识合规核查器 v1 |
| 2026-10-13 | 领域查证 | 《标识办法》国信办通字〔2025〕2 号 2025-09-01 施行；GB 45438-2025 强标 2025-09-01 实施、现行；2026 年内未见替代/修订 |
| 2026-10-13 | 开源空白核定 | 合规口径核查工具≈0；高 star 项目恰为**去水印反合规**方向；C2PA 为标准/解析库 → 空白 + 差异化明确 |
| 2026-10-13 | 伦理边界 | **明确非目标：不做去水印/标识规避**；工具定位合规辅助（写进 01 边界与 README） |
| 2026-10-13 | 厚度补强 | 因锚点为单一政策（无版本切换可用），靠**批量扫描对账 + 字段映射引擎 + 合成样本真值基准 + 证据指纹**四件套补厚度，避免沦为单文件校验脚本 |
| 2026-10-13 | 招牌模式选用 | 复用系列：versioned ruleset + 全量批处理 + 合成生成器带植入真值 + 指纹防篡改 |
| 2026-10-13 | 交付形态 | 桌面 exe（PySide6+PyInstaller onedir 双 exe）+ CLI 双形态（沿用系列惯例） |
| 2026-10-13 | 首期范围 | 办法 + GB 45438-2025 的文本/图片/音视频标识字段规范 |
| 2026-10-13 | **LLM 使用：不使用** | 纯确定性规则 + 结构化输入，无解析兜底需求 → 零 API、结论可复现（D04） |
| 2026-10-13 | 核心层零第三方依赖 | `dependencies=[]`；重件走 extras（gui/report/pkg/dev）（D05） |
| 2026-10-13 | 输入形态 | 首期主通路 = 标识卡 JSON（UMR）；解析通路 M2 起增量接入（D13） |
| 2026-10-13 | 判定语义 | `status ∈ {pass,fail,unknown,skipped}`，`unknown` 不计违规但计入待人工确认（D14） |
| 2026-10-13 | 待核对项 | ~~GB 45438-2025 隐式标识字段清单与显式位置要求；办法条号~~ → **M1 已逐条核对完成**（国标 19 页预览核对、办法 14 条全文核对；字段口径修正：服务提供者合并为 `content_producer`）（V1–V3 闭合） |
| 2026-10-13 | 未决待续 | ~~"2026 年是否新增配套国标/网信办新规"~~ → **M1 已核对**（2026-10-13 openstd 标准目录 + gov.cn 政策文件库逐页查询，**未见**替代/新增；写法保留"所列渠道未见"，不以未搜到证否）（V5 闭合） |
| 2026-10-13 | 适用性画像（M2） | 引入输入契约 `scenario`（authored/exported/propagated）+ `observed`（scope→bool）；4 条 pending 据此转 verified（D23） |
| 2026-10-13 | 解析通路（M2） | 首批载体 = PNG/JPEG/ISO BMFF（MP4·M4A）；纯 stdlib 结构解析 + **显式降级**；载荷包裹键数据驱动（D26） |
| 2026-10-13 | 判定语义（M2） | `unique` check_type（§6.1 c)；`skipped` 不参与分级，无适用规则 → `not_assessed`（D24/D25） |
| 2026-10-13 | 建条必要性（M2） | **不建**附录 E 预留字段与 §5.x 数值量阈值规则（核对记录未覆盖 → 不编造标准内容）（D27） |
| 2026-10-13 | 缓议清零（M2） | P1 **上位规章显式不纳入判定路径**；P2 解析通路首批载体定夺（详见 06 §三） |
| 2026-10-13 | 对账口径（M3） | 两轮对账主键 = **稳定身份键**（`card:<id>` / `file:<相对路径>`），非内容指纹——否则"已修复"永远检不出（D28） |
| 2026-10-13 | 确定性（M3） | 报告产物逐字节可复现**覆盖到 XLSX**：openpyxl 的文档属性/zip 条目时间戳全部钉死（D29） |
| 2026-10-13 | 退出码（M3） | `scan` 任一件 fail → 1；**失败件不改变退出码**（"未判定"≠"违规"，D30） |
| 2026-10-13 | 失败隔离（M3） | 批量单件异常记 `scan_error` 后继续；超大容器 `container_too_large` 跳过（NFR-8/D31） |
| 2026-10-13 | 分派单点（M3） | `check` 单件与 `scan` 批量共用 `engine.check_file`（防两条通路结论漂移，D32） |
| 2026-10-13 | 基准口径（M4） | 对账口径唯一实现 = `benchmark/cases.py`（非 pass = `fail ∪ unknown`，**未观测 scope 排除**）；真值库测试与基准共用（D33） |
| 2026-10-13 | 基准指标（M4） | 指标方向显式：准确率/检出率/一致率 `>=`，**误报率 `<=`（硬口径 0）**；空分母口径显式（D34） |
| 2026-10-13 | 基准算例（M4） | 期望值由**注入点**推出、合规取值**从规则库派生**；**不许改真值凑引擎**；引擎分支用例在临时合成数据目录跑（D35） |
| 2026-10-13 | 弃选项 | 弃"去水印/标识规避工具"（反合规）；弃"通用 C2PA 解析器"（标准库已占且非中国口径）；弃"水印算法逆向" |

## 里程碑

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 计划文档 00-06 定稿 + 可运行骨架（规则库加载器+status 门控+CLI+测试+CI） | ✅ 完成 2026-10-13 |
| M1 | 数据先行：标识规则库逐条挂原文核对 + 字段映射表 + 合成样本真值库 + 台账 | ✅ 完成 2026-10-13 |
| M2 | 显式/隐式核验引擎充实（真实规则驱动）+ 解析通路首批载体 + 算例回归 100% | ✅ 完成 2026-10-13 |
| M3 | 完整性判定 + 批量扫描：合规分级 + 目录批量 + 两轮对账 + 报告证据链 | ✅ 完成 2026-10-13 |
| M4 | 基准：字段规则/构造真值/批量对账三类扫描，指标进 README | ✅ 完成 2026-10-13 |
| M5 | 桌面交付：PySide6 界面 + PyInstaller 双 exe + 演示素材 + 技术报告 | ✅ 完成 2026-10-13 |
| M6 | 脱敏发布 GitHub + Release（exe）+ 收尾固化 | ✅ 完成 2026-10-13（已发布：仓库 + Release v0.1.0） |

> **M6 交付物**：`tools/audit_desensitize.py`（脱敏四步审计 + 探测器阳性/阴性对照；
> 命中分 block/advisory 两级 + 行内 `audit-allow` 放行）、`tests/test_audit_desensitize.py`（18 项）。
> 内容侧全量扫描**阻断项 0**；资产口径与版权口径复核通过；**提交邮箱已全历史改写为 GitHub noreply**
> （`filter-branch --env-filter` + 二次 tree-filter 清除留档自命中，验证 blob/patch 0 命中）。
> **已发布**：`yuluo554/ai-content-labeling-checker`（公开）+ **Release v0.1.0**（挂双 exe 的
> ASCII 命名 zip）；CI 8 job 全绿；发布物本体经 `gh release download` 下载核 sha256 + 中立目录冻结态自检。
> 收尾固化：`tools/README.md` 登记、`plan/05` M6 DoD、`plan/06` D41–D43 + P3 结论、本文件回写、README 状态。
> 完整留档见 [plan/RELEASE-M6.md](RELEASE-M6.md)（含首跑 CI 抓出的 3 处真实缺陷）。

> **M5 交付物**：`src/labelcheck/gui/`（`services.py` **唯一引擎调用点**且**零 Qt** +
> `format.py` 渲染 + `tabs.py` 六页签（单件核验/批量扫描/两轮对账/基准指标/规则库与依据/关于）+
> `main_window.py` 入口；GUI **只渲染引擎结果、零判定逻辑**，AST 守门锁死）、
> `src/labelcheck/packaging/`（`build_datas()` 数据白名单 + `verify_dist()` 冻结态验伪 +
> `assert_ready()` 前置检查）、CLI `gui` 子命令（函数体内惰性导入；`--check` 可加载性自检）、
> `tools/`（`build_exe.py` + `labelcheck.spec` + `entry_gui.py`/`entry_cli.py` +
> `verify_package.py` + `make_demo_assets.py`）、`docs/技术报告.md` + `docs/demo/`（截图 + GIF）。
> onedir **双 exe** 实测通过冻结态验伪（GUI `console=False` ≈158 MB / CLI `console=True` ≈13 MB，
> CLI 排除 Qt 但保留 openpyxl）；测试 **420 项**全绿（3.8/3.12 双通过，3.12 跳过 1 项 XLSX 用例）；
> 生成器 4 个 `--check` 位级一致；生效规则仍 27 条。

> **M4 交付物**：`src/labelcheck/benchmark/`（`cases.py` **单一实现源**（对账口径 + 三类算例）+
> `metrics.py`（指标方向显式）+ 三 runner）、CLI `bench` 子命令（`--only`/`--json`/`-v`；
> `cmd_not_implemented` 桩转实现）；指标进 README。三类基准在仓库真实数据上全部达标：
> **判定准确率 100%（30/30）、检出率 100%（23/23，目标 ≥0.95）、误报率 0%（0/11）、
> 对账集合一致率 100%（2/2）**；全量 0.12 s。测试 **354 项**全绿（3.8/3.12 双通过）；生效规则仍 27 条。
> 下一棒见 [HANDOFF-M5.md](HANDOFF-M5.md)。
>
> **M3 交付物**：`src/labelcheck/scan/`（批量扫描 `scanner.py` + 两轮对账 `diff.py`；
> 失败隔离、超大容器安全阀、进度到 stderr）、`src/labelcheck/report/`（`report.md`/`summary.csv`/
> `detail.csv`/`report.xlsx`[可选]/`evidence.json`；含报告自身 sha256）、
> `engine.check_file`（单件/批量**共用**分派）、CLI `scan` 子命令（`--out`/`--json`/`--baseline`/
> `--progress-every`/`--quiet`）。测试 **311 项**全绿（3.8/3.12 双通过）；生效规则仍 27 条。
> 下一棒见 [HANDOFF-M4.md](HANDOFF-M4.md)。
>
> **M2 交付物**：`src/labelcheck/parse/`（容器结构解析 + AIGC 载荷抽取 + 显式降级）、
> 适用性画像（`scenario`/`observed`，4 条 pending 转 verified → **27 条生效规则**）、
> `data/parse/fixtures.json`（11 例**真实容器字节**算例，解析→核验全对账）、
> `tools/gen_parse.py`（新增生成器，`--check` 位级一致）、§6.1 c) `unique` 规则、
> CLI `parse` 子命令 + `check` 容器分派 + `--scenario`。
> 测试 **242 项**全绿（3.8/3.12 双通过）。下一棒见 [HANDOFF-M3.md](HANDOFF-M3.md)。
>
> **M1 交付物**：`data/knowledge/raw/`（办法全文快照 + 国标逐页核对记录 + 两份上位规章全文）、
> `data/rules/**`（GB 45438-2025 22 条 verified + 办法 9 条 pending，registry 含 sha256）、
> `data/mapping/national-fields.json`（5 字段 verified）、`data/truth/`（8 例真值库，与引擎全对账）、
> `tools/gen_rulesets.py`、`gen_mapping.py`、`gen_samples.py`（三者 `--check` 位级一致守门）。
> `effective_ruleset()` 首次返回**非空**；测试 174 项全绿（3.8/3.12 双通过）。
>
> M0 交付物：`pyproject.toml`、`src/labelcheck/`（12 模块）、`data/rules/`（注册表 + 两份规则文件）、
> `tests/`（全离线）、`.github/workflows/ci.yml`（三矩阵）。
