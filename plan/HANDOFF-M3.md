# HANDOFF-M3：M2 → M3 交接快照

> **用法**：新对话读 `plan/HANDOFF-M3.md` 继续完成任务（会话启动命令给绝对路径即可）。
> **上一棒**：M2 显式/隐式核验引擎充实（真实规则驱动）+ 解析通路首批载体 + 适用性画像 + 算例回归 100% ✅ 完成 2026-10-13。
> **下一棒**：M3 完整性判定 + 批量扫描 + 两轮对账 + 报告/证据链导出（FR-6/7/8/9）。

---

## 一、M2 交付物（已落地，勿重复造）

**解析通路首批载体（M2 主任务，已完成）**：`src/labelcheck/parse/`

| 模块 | 职责 |
|---|---|
| `containers.py` | PNG（`tEXt`/`zTXt`/`iTXt`）、JPEG（`APP1`/`APP13`/`COM`）、ISO BMFF（`moov`/`meta`/`uuid`）结构解析；载体识别（M4A→audio） |
| `aigc.py` | 从元数据文本块中找 AIGC JSON 载荷（括号配平扫描），摊平为容器键→值；报载荷块数 |
| `__init__.py` | `parse_file` / `parse_bytes` → `ParseOutcome`（标识卡 + 可观测性事实 + 降级原因码） |

- 纯 stdlib（`struct`+`zlib`），**核心层零第三方依赖不变**；
- `card_id` 由**内容 sha256 派生**（`PARSED-<16 hex>`）→ 同字节同卡同报告；
- 载荷外层包裹键从**映射表 `parse_profile.payload_wrapper`** 读（数据驱动，代码里零政策键名）；
- **降级原因码**：`structure_broken` / `unsupported_container` / `no_aigc_payload` / `no_payload_wrapper_configured`。

**载体适用性画像**：`scenario`（`authored`/`exported`/`propagated`）+ `observed`（scope→bool）

- 规则 `only_if.scenario` 未命中 → `skipped`（**不是 fail**）；未知场景**加载期报错**；
- `observed[scope]=false` → 该 scope 全部 `unknown`（解析通路看不到显式标识）；
- **4 条 pending 转 verified**（唯一正当路径：先画像、再核对）：

| 条目 | 场景门控 | 依据 |
|---|---|---|
| `gb45438:implicit:content_propagator.presence` | `propagated` | §6.1 a) 4) |
| `gb45438:implicit:propagate_id.presence` | `propagated` | §6.1 a) 5) |
| `measures:explicit:export.file.label.presence` | `exported` | 办法第四条第二款 |
| `measures:propagation:platform.hint.presence` | `propagated` | 办法第六条 |

**规则库扩充**：§6.1 c) `unique` 规则（整块隐式标识上下文判定，只许 implicit scope）；
**不建**附录 E 预留字段与 §5.x 数值量阈值（核对记录未覆盖 → 不编造，见 plan/06 D27）。

**算例回归 100%**：`data/parse/fixtures.json`（11 例**真实容器字节**，base64）+
`tests/test_parse_regression.py`（解析 → 核验 → 对账，全绿）。

**生成器**：`tools/gen_parse.py`（第 4 个生成器，`--check` 位级一致）。

**CLI**：新增 `parse` 子命令；`check` 支持容器文件自动分派；`--scenario`；报告 `--json` 加 `parse` 块。

**测试**：**242 项全绿**（Python 3.8.8 与 3.12 双通过）；生效规则 **27 条**（待核对 7 条）。

**关键数字变化（对报告头/selfcheck 有影响）**：

| 指标 | M1 | M2 |
|---|---|---|
| 生效规则数 | 22 | **27**（+2 传播要素、+2 办法独有、+1 unique） |
| 待核对条目 | 11 | **7**（仅剩与国标同 target 的办法条目） |
| GB 规则 | 24（22 verified + 2 pending） | **25（全 verified）** |
| 办法规则 | 9（全 pending） | 9（**2 verified + 7 pending**） |

## 二、M2 关键口径变化（**与本 HANDOFF 同步的既定口径，改前先对照**）

| 变化 | 内容 | 影响面 |
|---|---|---|
| **输入契约扩展（追加式）** | `LabelCard` 追加 `scenario` / `observed` / `implicit_duplicate_keys`；旧卡缺省得默认值，**不破坏既有调用** | 模型/引擎/CLI/真值/基准 |
| **`Finding` 追加 `scenario`** | 记录"本条判定在哪个场景下作出"；规则声明场景在 `evidence.applies_to` | 报告/对账 |
| **分级收紧（重要）** | `assessed = {非 skipped}` 为空 → `not_assessed`。两条来路：① 规则全 pending；② 当前载体/场景下无规则适用 | `integrity`/CLI |
| **新 check_type `unique`** | §6.1 c)；需整块上下文，**不经 `evaluate()`**（该函数对它显式报错） | 规则库/加载期/engine.implicit |
| **办法文档 status** | 有 verified 条目 → 文档 `status` 随之 `verified`（D21 一致性守门） | registry/守门 |
| **映射表新增 `parse_profile`** | `{payload_wrapper, source_clause}` —— 解析载荷外层键的单一事实源 | mapping/parse |
| **解析算例用 base64** | `data/**` 为无 CR 文本资产；二进制直接入仓会误触 EOL 门 | data/守门 |

## 三、M3 待办（下一棒）

1. **批量扫描 `scan/`（FR-6）**：目录/清单投喂（**含容器文件**——解析通路已成，不能只收 JSON）；
   - 失败隔离：单件异常 → `findings=[{status:"unknown", code:"scan_error"}]`，**继续**（NFR-8）；
   - 进度：每 N 件向 stderr 一行（`--quiet` 关闭）；产出 `ScanResult{items, summary, failed}`；
   - **性能**：大目录分批；解析通路要防"超大容器拖慢"（已设 `MAX_BLOB`，仍需实测整目录耗时）。
2. **两轮对账（FR-7）**：以 **`card_id` 为主键**（不用文件名）；三类集：新增违规 / 已修复 / 持续违规；
   指纹变化单独记 `content_changed`。
   - **解析通路的 `card_id` 由内容哈希派生** → 内容一变 id 就变，这会**破坏按 card_id 对账**！
     处理：对账键须允许"显式 card_id 覆盖"或对解析件改按 `content_sha256` 配对（**M3 必须先定这一口径**）。
   - **✅ M3 定夺（plan/06 D28）**：改为**稳定身份键**——标识卡件 `card:<card_id>`（逻辑身份）、
     解析件/失败件 `file:<相对路径>`；`content_sha256` **不参与配对**，只作独立的 `content_changed` 标记。
     这样"修复"（内容变了）仍能按身份认出，改名也不会误判成"新增+消失"。
3. **报告与证据链（FR-8/9）**：MD/CSV/XLSX（openpyxl 缺失降级 CSV，exit 0 不崩）；
   `evidence.json` 含报告自身 sha256；`generated_at` 由调用方传入（两次导出逐字节一致）。
   - 报告须把 M2 的 **`scenario` / `observed` / 解析降级原因**写进"核查范围"与逐件明细
     （否则解析件会被误读成"显式合规"）。
4. **`scan`/`bench` 桩转实现**后，CLI 退出码语义扩展（沿用 0/1/2/3；批量"有 fail"是否仍为 1 须定）。
5. **上位规章**：M2 已定夺"**显式不纳入**"（见 plan/06 P1），M3 无需再动；若需引用措辞，取 §三 P1 结论。

## 四、关键命令速查

```bash
# 生成器（改数据唯一路径；--check 断言位级一致）——M2 起共 4 个
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py && py -X utf8 tools/gen_mapping.py \
  && py -X utf8 tools/gen_samples.py && py -X utf8 tools/gen_parse.py
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_parse.py --check

# 数据与自检
PYTHONPATH=src py -X utf8 -m labelcheck selfcheck
PYTHONPATH=src py -X utf8 -m labelcheck version

# 单件核验（标识卡通路 / 容器通路）
PYTHONPATH=src py -X utf8 -m labelcheck check data/samples/card-text-basic.json -v            # compliant, exit 0
PYTHONPATH=src py -X utf8 -m labelcheck check data/samples/card-image-metadata-stripped.json  # non_compliant, exit 1

# 容器解析（M2）：先解码算例字节再解析
PYTHONPATH=src py -X utf8 -c "
import base64,json,pathlib
fx=json.loads(pathlib.Path('data/parse/fixtures.json').read_text(encoding='utf-8'))
f=next(x for x in fx['fixtures'] if x['fixture_id']=='PARSE-PNG-0001')
pathlib.Path('build-tmp.png').write_bytes(base64.b64decode(f['bytes_b64']))"
PYTHONPATH=src py -X utf8 -m labelcheck parse build-tmp.png
PYTHONPATH=src py -X utf8 -m labelcheck check build-tmp.png -v          # partial（显式未观测）

# 场景切换
PYTHONPATH=src py -X utf8 -m labelcheck check data/samples/card-text-basic.json --scenario propagated -v

# 测试（两版本）
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -X utf8 -m pytest tests/ -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest tests/ -q

# 生效规则数（M2 后应为 27）
PYTHONPATH=src py -X utf8 -c "from labelcheck.paths import find_data_dir; from labelcheck.rules import effective_ruleset; r=effective_ruleset(find_data_dir()); print(r.verified_rule_count, r.pending_rule_count, r.coordinate)"
```

## 五、本机环境事实与坑（沿用 M0/M1，仅列实测）

- 解释器：`py -0p` → **3.8.8** 与 **3.12**；Windows 上 `python` 是商店占位符，**一律用 `py`**；命令加 `-X utf8`。
- **Python 3.8 无 `Path.write_text(newline=)`**——写 LF 必须 `open(..., newline="\n")`。
- **Git Bash 的 `/tmp` 与 Windows Python 不互通**：临时文件用工作区相对路径或 Python `tempfile`。
- **Git Bash 里 `python - <<'PY'`（heredoc）在本机是商店占位符**，会静默不执行（CI runner 上是真 python，无此问题）；
  本机验证此类片段用 `py -X utf8 - <<'PY'`。
- **`data/**` 必须零 CR**：解析算例含二进制，**不要**把 PNG/JPEG 直接落仓（会命中 EOL 门）——用 base64（已是本仓口径）。
- **零政策字面量门会扫 `parse/`**：政策键名（`ContentProducer`/`ProduceID`/`ReservedCode1`/目标 id 等）
  **不得出现在源码（含 docstring）**。M2 实测踩过一次（aigc.py docstring 贴了键名）——写注释时用"要素键/外层包裹键"这类**结构描述**。
- 抓官方页面：`curl -s -L --max-time 40 <url> -H "User-Agent: Mozilla/5.0"`；字符集按页面声明解码。
- 全项目测试**单次 <3 秒**，无需分批；跨平台结论**以 CI 为准，别拿本机全绿当证据**。

## 六、M2 DoD 逐项核对（已闭合）

- [x] 解析通路首批载体接入：PNG/JPEG/ISO BMFF → 同一 UMR；解析失败**显式降级**（4 个原因码）→ 引擎判 `unknown`
- [x] 载体适用性画像：`scenario` + `observed`；4 条 pending 据画像转 verified（带 `only_if.scenario`）
- [x] 算例回归 100%：11 例真实容器字节，解析 → 核验 → 对账全绿（含截断/无载荷/重复保留/三容器/三载体）
- [x] 规则库扩充：§6.1 c) `unique` 规则；预留字段/§5.x 数值量**必要性结论 = 不建**（plan/06 D27）
- [x] 上位规章（V4）结论：plan/06 P1 **显式不纳入**；P2 解析通路首批载体同批定夺
- [x] CLI `parse` 子命令 + `check` 容器分派 + `--scenario`；报告新增 `source`/`scenario`/`observed`/`parse` 块
- [x] 测试全绿（**242 项**，3.8/3.12 双通过）+ 4 个生成器 `--check` 位级一致 + `selfcheck` 生效 27 条

**偏差说明**：
1. **§5.x 数值量阈值未建规则**：M1 逐页核对记录（`data/knowledge/raw/gb45438-2025/*-verification.md`）
   对 §5.1–5.4 只记录到位置枚举与两要素构成，**未覆盖任何数值量**。为守住"绝不编造数值"红线，
   本次**不建**此类规则；若后续补核对（挂页码）确认存在阈值，再按版本化流程启用。
2. **纯文本载体不入解析通路**：文本无元数据容器，"哪段文字是标识"需语义判断，首期无法确定性判定
   → 交人工录入通路（`explicit` 字段）。已在 README 与 plan/06 P2 显式声明。

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
   M6 脱敏扫描须把它列进白名单（否则 hex/长串规则可能误报），并确认 `.gitattributes` 已把它当文本（当前 `data/**` 通配 `eol=lf`，无冲突）。
5. `data/**/_private/` 已在 `.gitignore`（M0 补齐），M6 复核。
