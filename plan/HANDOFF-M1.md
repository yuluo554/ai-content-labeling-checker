# HANDOFF-M1：M0 → M1 交接快照

> **用法**：新对话读 `plan/HANDOFF-M1.md` 继续完成任务（会话启动命令给绝对路径即可）。
> **上一棒**：M0（计划 00–06 定稿 + 可运行骨架）✅ 完成 2026-10-13。
> **下一棒**：M1 数据先行（规则库逐条挂原文核对 + 字段映射表 + 合成样本真值库 + 台账）。

---

## 一、当前进度（已落地，勿重复造）

**计划文档（全部定稿）**

| 文件 | 内容 |
|---|---|
| `plan/00-README总览.md` | 文档索引 / 决策摘要 / 里程碑状态 |
| `plan/01-题目详细定义.md` | 题目全文 v1（上游，勿改） |
| `plan/02-需求解读.md` | 12 痛点→能力、FR-1…FR-11、6 项非目标、NFR 带验证方式 |
| `plan/03-架构与技术选型.md` | 分层架构、目录布局、extras 分层、`find_data_dir` 四分支 |
| `plan/04-模块详设.md` | **实现契约**：UMR schema、退出码、规则库 schema、check_type 表、分级算法、报告/证据链、基准、守门清单、接口稳定性 |
| `plan/05-数据计划与里程碑.md` | 入库流程、生成器确定性设计、真值语义、M0–M6 DoD |
| `plan/06-决策记录.md` | D01–D17 决策 + V1–V5 待核对 + P1–P3 缓议 + 弃选项 |

**代码骨架（`src/labelcheck/`，核心层零第三方依赖）**

```
__init__.py      版本 / POSITIONING / DISCLAIMER
__main__.py      python -m labelcheck 入口
errors.py        退出码常量 + 异常类型（单一定义源）
paths.py         find_data_dir 四分支（显式 > 环境变量 > 冻结内嵌 > 源码/CWD 上溯）
rng.py           SplitMix64 确定性 RNG（金标准前 8 项已实测校验）
jsonio.py        LF 落盘 / 无时间戳 / sha256 / Decimal 友好加载
model/           LabelCard（输入校验）/ Finding / CheckReport
rules/           rule.py（Rule + evaluate 分派）、loader.py（registry + effective_ruleset 门控）
mapping/         FieldMapping / MappingTable / resolve_fields（声明序确定性归一 + 歧义检测）
engine/          explicit.py / implicit.py / integrity.py / pipeline.py（CLI 与 GUI 共用编排）
cli/             main.py（check / selfcheck / version 已实现；scan→M3、bench→M4 显式桩 exit 2）
```

**数据（`data/`）**

- `rules/registry.json`：2 份依据文档（labeling-measures、gb45438-2025），均 `status=pending`，`active` 指向 2025-09-01。
- `rules/labeling-measures/2025-09-01.json`：4 条规则，全 `pending`。
- `rules/gb45438-2025/2025-09-01.json`：7 条规则，全 `pending`。
- `mapping/national-fields.json`：4 个国标字段，全 `pending`。
- `samples/`：2 张示例标识卡（含"元数据被剥离但显式标识在"边界件）。

**测试（`tests/`，158 项全绿，3.8 与 3.12 双通过）**

`test_infra.py` `test_rules_gate.py` `test_mapping.py` `test_model.py` `test_engine_explicit.py`
`test_engine_implicit.py` `test_engine_integrity.py` `test_cli.py` `test_guard_imports.py`
`test_guard_data.py` `test_guard_ci.py` + `_support.py`（夹具构造器）

**CI**：`.github/workflows/ci.yml`（windows×{3.8,3.12} + ubuntu×3.12；`fetch-depth: 0`；含 CLI smoke 作业）。

## 二、下一里程碑（M1）待办

1. **抓原文入库**：`data/knowledge/raw/` 落《标识办法》与 GB 45438-2025 原文快照（curl 落盘，不用摘要工具转述；逐页核对 openstd 标准目录 + cac.gov.cn 政策法规栏，确认 2026-10 前无新配套规定）。
2. **逐条核对并转 verified**（**本里程碑主任务**）：
   - GB 45438-2025 **隐式标识字段清单**：生成合成内容属性信息 / 服务提供者名称 / 服务提供者编码 / 内容制作编号 —— 字段名、类型、取值范围以标准原文为准，每条挂条号 + 出处；
   - GB 45438-2025 **显式标识位置/形式要求**（文本/图片/音视频）—— `position` 规则的 `allowed` 枚举取值须可溯；
   - 《标识办法》条款编号与义务划分 —— 与 CAC 官方页一致；
   - 核对通过 → `status="verified"` + `clause.article` 填真实条号 + `source_url` + `verified_at`；**核不到保持 `pending` 并留档已查渠道**（绝不编造条号）。
3. **建 `tools/gen_rulesets.py`**：从确定性模板生成 `data/rules/<doc>/<ver>.json`（冻结产物：无时间戳、LF），回填 `registry.json` 的 `sha256`；配"再生成位级一致"守门测试。
   > 注意：loader 已实现**指纹校验**——`registry` 里 `sha256` 非 null 时会与文件实际内容比对，不一致即 exit 3。填 sha256 后必须与生成器输出一致。
4. **建 `data/mapping/national-fields.json` 真内容**：按标准原文核对字段名/别名/类型/取值，转 `verified`。
5. **建 `tools/gen_samples.py`**：合成样本 + 真值（固定 seed，`splitmix64`；植入缺陷按 `plan/05 §三.3` 枚举）；两次生成位级一致。
6. **台账回写**：`data/README.md` 登记全部资产（来源/许可/sha256）；`plan/00`、`plan/05` M1 DoD 打勾。
7. **验收**：`effective_ruleset()` 首次返回**非空**（有 verified 条目）；测试全绿；`labelcheck check data/samples/card-text-basic.json` 从 `not_assessed` 变为实际判定。

## 三、既定口径清单（**动了会打挂基准/测试，改前先对照**）

| 口径 | 现值 | 约束 |
|---|---|---|
| `LabelCard` 字段名 / `carrier` 枚举 | `card_id/carrier/content_sha256/explicit/implicit/source/notes`；`text/image/audio/video` | 见 plan/04 §十一 |
| `Finding.status` 语义 | `pass`/`fail`/`unknown`/`skipped`；**`unknown` 不计违规** | 测试锁死（`test_model.py`） |
| 合规等级 | `compliant`/`partial`/`non_compliant`/**`not_assessed`** | `not_assessed` = 无生效规则；**绝不把"没检查"写成 compliant** |
| 退出码 | 0=无违规 / 1=检出不合规 / 2=用法输入错 / 3=环境依赖错 | 单一定义源 `errors.py`，`test_cli.py` 逐码锁死 |
| `effective_ruleset(data_dir)` | 双重门控：文档 `verified` **且**条目 `verified` | 唯一门控点（`test_rules_gate.py`） |
| `find_data_dir(explicit, require)` | 显式 > 环境变量 > 冻结内嵌 > 源码/CWD 上溯 | `test_infra.py` 锁死 |
| 规则 `check_type` | `presence/position/enum/pattern/type/range` | `Rule.evaluate` 分派 |
| 归一确定性 | 命中顺序 = 映射表**声明序**；`keys = [national_field] + aliases` | 不看 set/dict 迭代序 |
| 零政策字面量 | `test_guard_data.py::FORBIDDEN_POLICY_TOKENS` | 规则取值不得硬编码进引擎源码 |
| 产物确定性 | 无时间戳（`generated_at` 由调用方传入）；LF 落盘 | `test_guard_data.py` 扫描时钟调用 |
| CLI 顶层禁 GUI | AST 断言 | `test_guard_imports.py` |
| CI checkout | 必须 `fetch-depth: 0` | `test_guard_ci.py` |

## 四、本机环境事实与坑（只写实测过的）

- 解释器：`py -0p` → **3.8.8**（`C:\Users\ASUS\AppData\Local\Programs\Python\Python38`）与 **3.12**。
  Windows 上 `python` 是商店占位符，**一律用 `py`**；跑命令加 `-X utf8`（中文控制台）。
- **Git Bash 的 `/tmp` 与 Windows Python 不互通**：写临时文件用 Python 自己的 `tempfile`，或工作区相对路径（实测踩过：`/tmp/x.yml` 用 `py` 读会 `FileNotFoundError`）。
- 跑测试（无需安装）：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -X utf8 -m pytest tests/ -q`。
- 跑 CLI 未安装时：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -X utf8 -m labelcheck <cmd>`。
- `py -X utf8` **掩盖**非 ASCII 输出缺口（CI 管道是 cp1252 会崩）→ CLI 入口已加 `_ensure_utf8_stdio()`；跨平台结论**以 CI 为准，别拿本机全绿当证据**。
- pip 若被系统代理污染：`NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`。
- 全项目测试**单次 <1 秒**，无需分批。

## 五、M0 DoD 逐项核对（已闭合）

- [x] plan/02–06 五份文档定稿（需求解读 / 架构选型 / 模块详设 / 数据计划 / 决策记录）
- [x] `plan/00` 索引、里程碑与决策摘要回写 ✅
- [x] `pyproject.toml`（`src` 布局、`dependencies=[]`、extras: dev/report/gui/pkg、console_scripts）
- [x] `src/labelcheck/` 12 模块可 import，核心层零第三方（AST 守门）
- [x] 规则库加载 + **status 双重门控** + 指纹校验 + 版本坐标
- [x] 字段映射引擎（声明序确定性归一 + 跨字段歧义检测）
- [x] 显式/隐式/完整性三核验器 + 端到端编排（CLI 与未来 GUI 共用）
- [x] CLI `check`/`selfcheck`/`version` 实跑通过；`scan`/`bench` 显式未实现桩（exit 2）
- [x] 退出码 0/1/2/3 逐码测试锁死
- [x] 测试 **158 项全绿**（Python 3.8.8 与 3.12 双通过），含失败路径
- [x] 守门测试：EOL+阳性对照 / splitmix64 金标准 / 门控 / AST import / 零政策字面量 / 无时钟 / CI workflow 可解析（含"冒号+空格"阳性对照）+ `fetch-depth: 0`
- [x] CI 三矩阵配置 + 本地 YAML 可解析校验通过
- [x] 数据骨架全 `pending`，门控行为经 CLI 实测可观测（`not_assessed`）
- [x] README（能力/快速开始/退出码/结构/里程碑/限制与免责）+ `data/README.md` 台账回写
- [x] 本 HANDOFF 落盘

**偏差说明**：无。M0 未做真实条文核对（属 M1 范围，已在计划中标明）；`scan`/`bench` 为显式桩（M3/M4），桩以 exit 2 + 明确提示呈现，不静默假装成功。

## 六、关键命令速查

```bash
# 数据与自检
PYTHONPATH=src py -X utf8 -m labelcheck selfcheck
PYTHONPATH=src py -X utf8 -m labelcheck version

# 单件核验（当前预期：not_assessed，因规则全 pending）
PYTHONPATH=src py -X utf8 -m labelcheck check data/samples/card-text-basic.json -v
PYTHONPATH=src py -X utf8 -m labelcheck check data/samples/card-image-metadata-stripped.json --json

# 测试
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -X utf8 -m pytest tests/ -q
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest tests/ -q     # 跨版本

# 查看现行生效规则数（M1 前应为 0）
PYTHONPATH=src py -X utf8 -c "from labelcheck.paths import find_data_dir; from labelcheck.rules import effective_ruleset; r=effective_ruleset(find_data_dir()); print(r.verified_rule_count, r.pending_rule_count, r.coordinate)"
```
