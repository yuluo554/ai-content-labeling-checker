# HANDOFF-M5：M4 → M5 交接快照

> **用法**：新对话读 `plan/HANDOFF-M5.md` 继续完成任务（会话启动命令给绝对路径即可）。
> **上一棒**：M4 三类内置评测基准（`benchmark/`，FR-11）+ 指标进 README ✅ 完成 2026-10-13。
> **下一棒**：M5 桌面交付——PySide6 界面 + PyInstaller onedir 双 exe + 演示素材 + 技术报告。

---

## 一、M4 交付物（已落地，勿重复造）

**内置基准**：`src/labelcheck/benchmark/`

| 模块 | 职责 |
|---|---|
| `cases.py` | **单一实现源**：对账口径（`observed_nonpass`/`compare_nonpass`）+ 三类算例构造 + 用例判定 |
| `metrics.py` | `Metric`（值 + 方向 `>=`/`<=` + 阈值）、`SuiteResult`、`BenchReport`；`rate(..., empty=)` 空分母口径显式 |
| `runner_fields.py` | `fields` 基准（30 例：逐 check_type 的边界/畸形用例）→ 判定准确率 |
| `runner_constructed.py` | `constructed` 基准（34 例 = 随附真值库 8 + 程序化构造 26）→ 检出率 / 误报率 |
| `runner_diff.py` | `diff` 基准（2 场景：两轮对账全集合）→ 对账集合一致率 |
| `__init__.py` | `run_benchmark(data_dir, only=None, work_dir=None) -> BenchReport`；`BENCH_NAMES` |

**CLI**：`bench`（`--only NAMES` / `--json` / `-v`）；退出码 **0 达标 / 1 未达标 / 2 用法错误**。
`cmd_not_implemented(args, "M4")` 分支**已删除**，`bench` 进 handlers（桩函数本体保留但无调用点）。

**实测指标（仓库真实数据）**：

| 基准 | 指标 | 实测 | 达标线 |
|---|---|---|---|
| `fields` | 判定准确率 | **100%**（30/30） | 100% |
| `constructed` | 检出率 | **100%**（23/23） | ≥ 95% |
| `constructed` | 误报率 | **0%**（0/11） | 0（硬口径） |
| `diff` | 对账集合一致率 | **100%**（2/2） | 100% |

**全量单次 0.12 s**（要求 <1 s）。指标表已进 `README.md`。

**测试**：**354 项全绿**（Python 3.8.8 与 3.12 双通过；3.12 无 openpyxl → XLSX 确定性用例自动 skip）。
新增测试文件：`test_benchmark_cases.py`（17）、`test_benchmark_runner.py`（13）、
`test_benchmark_cli.py`（7）；`test_cli.py` 的 bench 桩用例改写为 4 项实现用例；
`test_guard_imports.py` 增 `benchmark/` 零第三方 + 零时钟守门；
`test_generators.py` 的引擎对账改为**共用** `benchmark.cases` 的对账函数。

## 二、M4 关键口径（**与本 HANDOFF 同步的既定口径，改前先对照**）

| 变化 | 内容 | 影响面 |
|---|---|---|
| **对账口径唯一实现**（D33） | 非 pass = `fail ∪ unknown`；**未观测的 scope 排除在比较之外**；实现在 `benchmark/cases.py`，真值库测试（`test_generators.py`）与解析回归（`test_parse_regression.py`）**共用** | 基准/测试 |
| **指标方向显式**（D34） | `Metric.op ∈ {">=", "<="}`：准确率/检出率/一致率 `>=`；**误报率 `<=`（硬口径 0）**；空分母口径显式（`rate(..., empty=)`） | 基准/README |
| **算例期望值不抄引擎**（D35） | 期望由**注入点**推出；合规取值/位置/枚举**从规则库派生**（`valid_implicit_value`/`explicit_element`/`pattern_fragments`）；**不许改真值凑引擎** | `benchmark/cases.py` |
| **引擎分支用例** | 未映射字段 → `unknown`；无适用规则 → `not_assessed`；在**临时合成数据目录**跑（`build_synthetic_data_dirs`），跑完即删，不污染仓库 | 基准/守门 |
| **`bench` 退出码** | `0` 达标 / `1` 未达标 / `2` 用法错误（与 `check`/`scan` 的 1 = 检出问题一致） | CLI |
| **`forbid` 断言纪律** | 只许禁止**带具体原因码**的判定，**不得**禁止裸 `pass`（同 target 常有多条规则，会撞车） | 基准算例 |

**未覆盖项（如实记录，不假装覆盖）**：`range` check_type 在生效规则库中**不存在**
（M2 建条决策 D27 显式判定"不建"）→ `fields` 基准在 `notes` 里如实说明"该类用例未生成"。

## 三、M5 待办（下一棒）

1. **PySide6 界面**（`src/labelcheck/gui/`，FR-12）：
   - 页签：单件核验 / 批量扫描 / 两轮对账 / 基准指标 / 规则库与依据；
   - **GUI 只渲染引擎结果，零判定逻辑**（`plan/03` §二 分层图）——只调 `engine.check_file` /
     `scan_target` / `diff_scans` / `run_benchmark`，不得在 GUI 里重写任何判定或分派；
   - 依赖走 optional extra `gui`（`PySide6`，**本机 3.8 需锁版本上限**，系列实测 6.6.3.1 为 3.8
     可解析最高）；GUI 相关测试用 `pytest.importorskip("PySide6")` 声明式跳过。
2. **PyInstaller onedir 双 exe**（`src/labelcheck/packaging/`）：
   - 双 exe = GUI（`console=False`）+ CLI 控制台（`console=True`）；
   - `build_datas()` 白名单：把 `data/` 内嵌进 dist（`rules`/`mapping`/`truth`/`parse`/`samples`/
     `knowledge`）；**构建后校验**解析到的数据目录**落在 dist 之内**（`find_data_dir` 冻结态分支）；
   - 干净验证在中立目录（`%LOCALAPPDATA%\Temp`）+ `env -i` 下跑（防"验了个寂寞"）。
3. **演示素材**（`docs/demo/`，`tools/make_demo_assets.py`）：截图 + GIF，进 README。
4. **技术报告**（`docs/`）：标识规则化方法、元数据映射设计、批量与证据链、**基准指标**。
5. **plan 回写**：`plan/04` 补 GUI/打包章节；`plan/03` 回写 GUI/packaging 状态；`plan/06` 补 M5 决策。

## 四、关键命令速查

```bash
# 内置基准（M4；仓库真实数据下必须全部达标 → exit 0）
PYTHONPATH=src py -X utf8 -m labelcheck bench
PYTHONPATH=src py -X utf8 -m labelcheck bench -v
PYTHONPATH=src py -X utf8 -m labelcheck bench --only fields,diff --json

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

# 批量扫描 + 报告 + 两轮对账（M3）
PYTHONPATH=src py -X utf8 -m labelcheck scan data/samples --out build-out -v
PYTHONPATH=src py -X utf8 -m labelcheck scan data/samples --json > build-round1.json
PYTHONPATH=src py -X utf8 -m labelcheck scan data/samples --baseline build-round1.json

# 测试（两版本）
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -X utf8 -m pytest tests/ -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest tests/ -q

# 生效规则数（M2 后应为 27）
PYTHONPATH=src py -X utf8 -c "from labelcheck.paths import find_data_dir; from labelcheck.rules import effective_ruleset; r=effective_ruleset(find_data_dir()); print(r.verified_rule_count, r.pending_rule_count, r.coordinate)"
```

## 五、本机环境事实与坑（沿用 M0–M4，仅列实测）

- 解释器：`py -0p` → **3.8.8** 与 **3.12**；Windows 上 `python` 是商店占位符，**一律用 `py`**；命令加 `-X utf8`。
- **Python 3.8 无 `Path.write_text(newline=)`**——写 LF 必须 `open(..., newline="\n")`。
- **Git Bash 的 `/tmp` 与 Windows Python 不互通**：临时文件用工作区相对路径或 Python `tempfile`。
- **Git Bash 里 `python - <<'PY'`（heredoc）在本机是商店占位符**，会静默不执行；本机验证用 `py -X utf8 - <<'PY'`。
- **`data/**` 必须零 CR**：解析算例含二进制，**不要**把 PNG/JPEG 直接落仓（会命中 EOL 门）——用 base64。
- **零政策字面量门会扫 `benchmark/`**（M4 起）：政策键名/目标 id **不得出现在源码（含 docstring）**；
  且 **`datetime.now(` / `time.time()` 等系统时钟 token 也不得出现（含注释）**——M3 踩过一次、
  M4 又踩过一次（`cases.py` docstring 里写了字段名被命中）。写注释时用"生成合成属性要素"这类表述。
- **同一 target 常有多条规则**：写基准断言时 `forbid` 只禁带原因码的判定，**别禁裸 `pass`**（会撞车）。
- **openpyxl 只在本机 3.8 有（3.1.5），3.12 无**——XLSX 相关测试用 `pytest.importorskip` 或
  `monkeypatch` 造缺失路径；CI 的 core-only job 天然走降级路径。
- 全项目测试**单次约 5 秒**（含基准），无需分批；跨平台结论**以 CI 为准，别拿本机全绿当证据**。

## 六、M4 DoD 逐项核对（已闭合）

- [x] **三类内置基准（FR-11）**：`fields`（30 例）/ `constructed`（34 例）/ `diff`（2 场景）；
      一条命令跑全（CLI `bench`），退出码 0/1/2
- [x] **指标达标（仓库真实数据）**：判定准确率 100%、检出率 100%（≥0.95）、误报率 0%、对账一致率 100%
- [x] **零 API / 纯规则通路**：`benchmark/` 零第三方顶层依赖 + 零系统时钟（守门）；全量 0.12 s（<1 s）
- [x] **单一实现源**：`benchmark/cases.py` 的对账口径被真值库测试与解析回归**共用**；
      期望值由注入点推出、取值从规则库派生；**不许改真值凑引擎**
- [x] **复用既有真值**：`data/truth/`（8 例）+ `data/parse/fixtures.json`（11 例）仍逐例跑；不另造一套
- [x] **指标进 README**：三类基准的指标表 + 口径说明 + 复现命令
- [x] `bench` 桩转实现：`cmd_not_implemented(args, "M4")` 分支删除，`bench` 进 handlers；CI 增 bench 冒烟
- [x] 测试全绿（**354 项**，3.8/3.12 双通过）+ 4 个生成器 `--check` 位级一致 + `selfcheck` 生效 27 条
- [x] `plan/04 §九` 按实现回写；`plan/06` 回写 D33–D35；`plan/05` 加 M4 DoD；README/data-README/CI 同步

**偏差说明**：

1. **`range` check_type 无规则可测**：仓库生效规则库中不存在 `range` 类型（M2 建条决策 D27 显式
   判定"不建"）→ `fields` 基准在 `notes` 里如实说明"该类用例未生成"，**不假装覆盖**。若 M5/M6
   因新核对记录建了 `range` 规则，基准会自动开始覆盖（`missing_check_types` 驱动）。
2. **`fields` 的 `forbid` 形态**：初版对隐式字段写了"不得 pass"，与同 target 的 `unique`/`presence`
   规则撞车（同一 `content_property` 被 presence+enum+unique 三条判定）——改为**只禁带原因码的判定**。
   这是断言写法问题，不是引擎问题；已把该纪律写进 `cases.py` 模块 docstring。
3. **`content_changed` 在 diff 场景里含"已修复件"**：A 件上轮违规、本轮修复（内容必变）→ 同时进
   `fixed` 与 `content_changed`。这是既定口径（D28：指纹变化独立标记，不退化成新增+移除），
   基准期望据此声明 `["card:A", "card:B"]`。
4. **`bench` 的 `--json` 含 `data_dir` 绝对路径**：与本机路径绑定（同 M3 报告产物口径）——
   CI 只断言 `passed` 与 suite 名，**不比对整份 JSON 字节**；报告产物不入仓。

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
6. **M3/M4 新增文件不得带真实路径/主机名**：报告 `root` 字段写的是用户传入路径（本机为
   `D:\ProgramData\...`）——**报告产物不入仓**（由调用方输出目录决定），M6 确认 `.gitignore`
   已排除常见报告输出目录（`build-*/`、`scan-out*/` 等）。
7. **M5 新增的 exe/dist 产物不入仓**：`dist/`、`build/`、`*.spec` 的 `dist` 输出须在 `.gitignore`；
   Release 只挂 exe（M6），仓库只留构建脚本。