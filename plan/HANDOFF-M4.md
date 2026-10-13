# HANDOFF-M4：M3 → M4 交接快照

> **用法**：新对话读 `plan/HANDOFF-M4.md` 继续完成任务（会话启动命令给绝对路径即可）。
> **上一棒**：M3 完整性判定 + 批量扫描 + 两轮对账 + 报告/证据链导出（FR-6/7/8/9）✅ 完成 2026-10-13。
> **下一棒**：M4 三类内置评测基准（`benchmark/`，FR-11）+ 指标进 README。

---

## 一、M3 交付物（已落地，勿重复造）

**批量扫描 + 两轮对账**：`src/labelcheck/scan/`

| 模块 | 职责 |
|---|---|
| `scanner.py` | 目录/清单/单文件投喂 → 逐件核验 → `ScanResult`；**失败隔离**；超大容器安全阀；进度到 stderr |
| `diff.py` | 两轮对账：`added`/`fixed`/`persistent`（含 `changed_targets`）/`stable` + `new_items`/`removed`/`content_changed` |
| `__init__.py` | `scan_target` / `scan_paths` / `iter_input_paths` / `ScanResult` / `ScanItem` / `diff_scans` / `DiffResult` |

**报告 + 证据链**：`src/labelcheck/report/`

| 产物 | 说明 |
|---|---|
| `report.md` | 固定骨架：报告头 / **强制免责声明** / 核查范围（含 scenario·observed·解析降级）/ 依据清单 / 逐件逐字段 / 违规清单（按 severity）/ 失败件清单 / 两轮对账 / 结论 |
| `summary.csv` | 每件一行（含 fail/review 目标、解析降级原因、失败原因） |
| `detail.csv` | 每 finding 一行（含条款、observed/expected） |
| `report.xlsx` | `openpyxl` 可用时产出；**缺失 → 只导 CSV + 提示，exit 0 不崩** |
| `evidence.json` | 每件 `content_sha256` + 规则库坐标 + **报告自身 sha256** + `artifacts{name→sha256}` |

**引擎单点分派**：`engine.check_file(path, data_dir, ...) -> (CheckReport, ParseOutcome|None)`
——`check` 单件与 `scan` 批量**共用**（plan/06 D32），杜绝两条通路结论漂移。
`engine.with_scenario(card, scenario)` 供 CLI `--scenario` 覆盖。

**CLI**：`scan <DIR|MANIFEST>`（`--out` / `--json` / `--baseline` / `--progress-every` / `--quiet`
/ `--generated-at` / `--scenario` / `-v`）；退出码沿用 0/1/2/3。

**测试**：**311 项全绿**（Python 3.8.8 与 3.12 双通过；3.12 无 openpyxl → XLSX 确定性用例自动 skip）。
新增测试文件：`test_scan.py`（19）、`test_scan_diff.py`（14）、`test_report.py`（15）、`test_evidence.py`（10），
`test_cli.py` 增批量扫描段，`test_guard_imports.py` 增 scan/report 惰性导入守门。

## 二、M3 关键口径（**与本 HANDOFF 同步的既定口径，改前先对照**）

| 变化 | 内容 | 影响面 |
|---|---|---|
| **对账主键 = 稳定身份键**（D28） | 标识卡件 `card:<card_id>`（逻辑身份，与文件名/内容无关）；解析件/失败件 `file:<相对路径>`。**不用**内容指纹——解析件 `card_id` 由内容派生，按它配对会让"已修复"永远检不出 | `scan/diff.py` |
| **`content_changed` 独立标记** | 身份不变而 `content_sha256` 变 → 如实标出，**不**退化成"新增+移除" | 对账/报告 |
| **XLSX 时间戳钉死**（D29） | openpyxl 的 `docProps/core.xml` 时间戳与 zip 条目 `date_time` 全部钉死（`generated_at` 可解析时用之，否则固定基准 `2025-01-01T00:00:00`；zip 条目 `(1980,1,1,0,0,0)`） | `report/` 确定性 |
| **批量退出码**（D30） | 任一件 fail → 1；**失败件不改变退出码**（"未判定"≠"违规"） | CLI/scan |
| **失败隔离**（D31） | 单件异常记 `kind="failed"`、`code=scan_error` 后继续；超大容器 `container_too_large` 跳过（默认 512 MiB） | scan |
| **分派单点**（D32） | `check` 单件与 `scan` 批量共用 `engine.check_file` | engine/CLI |
| **`Ruleset.doc_versions` 扩展** | 追加 `title`/`doc_number`/`issuer`/`kind`/`effective_from`（报告"依据清单"直接取用，单一来源） | rules/报告 |
| **`ScanItem.identity` 冲突消解** | 同键按发现序加序号（`#2`…），**不丢件** | scan |

**实测性能（HANDOFF-M3 §三.1 要求）**：1000 张标识卡（一半合规一半缺字段）单目录扫描
**2.478 s（约 2.5 ms/件）**；解析通路侧由 `MAX_BLOB`（单块 4 MiB）+ `MAX_CONTAINER_BYTES`
（单件 512 MiB，超出跳过）双阀防"超大容器拖慢/拖垮"。**无分批必要**（<3 s / 千件）。

## 三、M4 待办（下一棒）

1. **三类内置基准（FR-11）**：`src/labelcheck/benchmark/` + CLI `bench`（M4 桩转实现）。
   | 基准 | 内容 | 指标 |
   |---|---|---|
   | `fields` | 元数据字段 存在性/类型/格式/取值 的枚举用例（含边界与畸形输入） | 判定准确率（目标 100% 确定性用例） |
   | `constructed` | 程序化构造带**已知标识配置**的合成件（正确/缺字段/错位置/错取值） | 检出率 ≥0.95 / 误报率 0 |
   | `diff` | 两轮扫描差异对账的确定性验证 | 对账三类集合完全一致 |
   - 三类 runner 一条命令跑全，退出码 `0` 达标 / `1` 未达标 / `2` 用法错误；**全量单次 <1 秒**；
   - **零 API 依赖**（纯规则通路）；
   - **对账口径**（plan/05 §三.2）：比对 `expected` 声明的**非 pass 集合**与引擎实际非 pass 集合，
     单一实现源（`benchmark/cases.py`）供测试与基准共用；**不许改真值凑引擎**。
2. **指标进 README**（可信度核心证据）：三类基准的指标表。
3. **复用既有真值**：`data/truth/`（8 例标识卡）+ `data/parse/fixtures.json`（11 例容器）已是现成算例，
   基准可直接消费（勿另造一套）；`benchmark/cases.py` 应与 `tests/test_generators.py`
   的引擎对账口径同源。
4. **`bench` 桩转实现后**：`cmd_not_implemented(args, "M4")` 分支删除，`bench` 进 handlers。

## 四、关键命令速查

```bash
# 生成器（改数据唯一路径；--check 断言位级一致）——M2 起共 4 个
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py && py -X utf8 tools/gen_mapping.py \
  && py -X utf8 tools/gen_samples.py && py -X utf8 tools/gen_parse.py
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_parse.py --check

# 数据与自检
PYTHONPATH=src py -X utf8 -m labelcheck selfcheck
PYTHONPATH=src py -X utf8 -m labelcheck version

# 单件核验
PYTHONPATH=src py -X utf8 -m labelcheck check data/samples/card-text-basic.json -v            # compliant, exit 0
PYTHONPATH=src py -X utf8 -m labelcheck check data/samples/card-image-metadata-stripped.json  # non_compliant, exit 1

# 批量扫描 + 报告（M3）
PYTHONPATH=src py -X utf8 -m labelcheck scan data/samples --out build-out -v
PYTHONPATH=src py -X utf8 -m labelcheck scan data/samples --json > build-round1.json
PYTHONPATH=src py -X utf8 -m labelcheck scan data/samples --baseline build-round1.json   # 两轮对账

# 测试（两版本）
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -X utf8 -m pytest tests/ -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest tests/ -q

# 生效规则数（M2 后应为 27）
PYTHONPATH=src py -X utf8 -c "from labelcheck.paths import find_data_dir; from labelcheck.rules import effective_ruleset; r=effective_ruleset(find_data_dir()); print(r.verified_rule_count, r.pending_rule_count, r.coordinate)"
```

## 五、本机环境事实与坑（沿用 M0–M2，仅列实测）

- 解释器：`py -0p` → **3.8.8** 与 **3.12**；Windows 上 `python` 是商店占位符，**一律用 `py`**；命令加 `-X utf8`。
- **Python 3.8 无 `Path.write_text(newline=)`**——写 LF 必须 `open(..., newline="\n")`。
- **Git Bash 的 `/tmp` 与 Windows Python 不互通**：临时文件用工作区相对路径或 Python `tempfile`。
- **Git Bash 里 `python - <<'PY'`（heredoc）在本机是商店占位符**，会静默不执行；本机验证用 `py -X utf8 - <<'PY'`。
- **`data/**` 必须零 CR**：解析算例含二进制，**不要**把 PNG/JPEG 直接落仓（会命中 EOL 门）——用 base64。
- **零政策字面量门会扫 `scan/`、`report/`**：政策键名/目标 id **不得出现在源码（含 docstring）**；
  且 **`datetime.now(` / `time.time()` 等系统时钟 token 也不得出现（含注释）**——M3 实测踩过一次
  （report 模块注释里写了 `datetime.now()` 被 `test_no_timestamps_written_by_engine_sources` 命中），
  写注释时用"当前时刻"这类表述。
- **openpyxl 只在本机 3.8 有（3.1.5），3.12 无**——XLSX 相关测试用 `pytest.importorskip` 或
  `monkeypatch` 造缺失路径；CI 的 core-only job 天然走降级路径。
- 全项目测试**单次 <4 秒**，无需分批；跨平台结论**以 CI 为准，别拿本机全绿当证据**。

## 六、M3 DoD 逐项核对（已闭合）

- [x] **批量扫描（FR-6）**：目录（含容器文件）/清单/单文件投喂；逐件走 `engine.check_file`；
      失败隔离（`scan_error`/`container_too_large`，整批不中断，NFR-8）；超大容器安全阀；
      进度每 N 件一行到 stderr（`--quiet` 关闭）；`ScanResult{items, summary, failed, ruleset}` 可复现
- [x] **两轮对账（FR-7）**：`added`/`fixed`/`persistent`（含 `changed_targets`）/`stable`
      + `new_items`/`removed`/`content_changed`；**配对主键 = 稳定身份键**（D28）；确定性
- [x] **报告与证据链（FR-8/9）**：`report.md`（固定骨架 + 强制免责声明 + M2 口径进报告）/
      `summary.csv`/`detail.csv`/`report.xlsx`（缺失降级 CSV，exit 0 不崩）/`evidence.json`
      （每件指纹 + 报告自身 sha256 + artifacts 哈希）
- [x] **确定性（NFR-3）**：相同输入两次导出**逐字节一致**（含 XLSX：时间戳钉死，D29）
- [x] **退出码扩展**：`scan` 0/1/2/3；任一件 fail → 1；失败件不改退出码（D30）
- [x] 测试全绿（**311 项**，3.8/3.12 双通过）+ 4 个生成器 `--check` 位级一致 + `selfcheck` 生效 27 条
- [x] `plan/04 §七/§八` 按实现回写；`plan/06` 回写 D28–D32；`plan/05` 加 M3 DoD；README/data-README/CI 同步

**偏差说明**：

0. **HANDOFF-M3 §三.4 的口径落点**：该条要求"`scan`/`bench` 桩转实现后，CLI 退出码语义扩展
   （批量"有 fail"是否仍为 1 须定）"。**M3 只转 `scan` 桩**（`bench` 按 plan/04 §二.1 与
   plan/05 里程碑表属 **M4/FR-11**，仍在 `cmd_not_implemented(args, "M4")` 桩上，exit 2）。
   该条的**实质交付 = 批量退出码口径定夺**，已由 **plan/06 D30**（任一件 fail → 1；失败件不改退出码）
   与 plan/04 §8.4 闭合。
1. **对账辅助集扩充**：计划原列"三类集"，实现补 `stable`（两轮均无违规）与 `new_items`/`removed`
   两个辅助集——报告与 CLI 需要完整呈现件级去向（"没出现在任何集合里"会让用户以为漏扫）。
2. **`content_changed` 只在双方指纹都在时判"变动"**：失败件读不到字节（指纹空）时既不冒充"未变动"
   也不冒充"已变动"，由证据里的空指纹体现"无从比较"。
3. **`scan` 的 `--baseline` 读 `ScanResult` JSON**（`scan --json` 的产物），不另设专用格式——
   避免第二份结果格式。

## 七、留给 M6（发布）的必办项（**勿忘**）

1. **提交元数据邮箱是真实个人邮箱**（`git log --format="%ae %ce"` 可见）——发布前须用
   `filter-branch --env-filter` 全历史改写为 GitHub noreply，并同步 `git config user.email`。
   **历史重写属对外结构性动作，须用户明确授权**后再做（skill 阶段 7）。
2. **脱敏扫描的已知假阳性**：示例标识卡里的假 sha256 hex 串（64 个连续 hex 字符）会命中"18 位身份证"
   正则。M6 审计脚本须给 phone/idcard 模式加 **hex 边界环视** `(?<![0-9a-fA-F])…(?![0-9a-fA-F])`，
   并把该形态写进 selftest 阴性对照。
3. **`data/knowledge/raw/` 的版权口径**：办法全文为行政公文（可留档）；国标**不转载全文**，
   只留书目元数据 + 条号要点对照（已按此办理，M6 复核一遍）。
4. **`data/parse/fixtures.json` 的字节形态**：内含 base64 的构造容器（非真实媒体），
   M6 脱敏扫描须把它列进白名单（否则 hex/长串规则可能误报），并确认 `.gitattributes` 已把它当文本。
5. `data/**/_private/` 已在 `.gitignore`（M0 补齐），M6 复核。
6. **M3 新增文件不得带真实路径/主机名**：报告 `root` 字段写的是用户传入路径（本机为
   `D:\ProgramData\...`）——**报告产物不入仓**（由调用方输出目录决定），M6 确认 `.gitignore`
   已排除常见报告输出目录（`build-*/`、`scan-out*/` 等）。