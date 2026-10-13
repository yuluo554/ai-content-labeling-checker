# data/ 数据台账

> 规则（ai-tool-project-sprint 阶段 1）：每份数据登记来源与许可；规范条目挂出处 + status（`verified`/`pending`）；程序化自制带真值数据是核心资产（固定输入可复现）。`_private/` 目录不入仓。
> 纪律：**未挂原文核对不得落库/生效/进入判定路径**；搜索摘要一律不采信，字段规范以标准原文/官方页面直连核对。

## 一、登记表（M2 更新）

| 数据 | 类型 | 来源 | 许可/版权口径 | 状态 |
|---|---|---|---|---|
| `data/rules/registry.json` | 依据文件注册表 | **生成器产出**（`tools/gen_rulesets.py`） | 自制（含文号/标准号元信息） | ✅ M2（含 sha256 指纹） |
| `data/rules/labeling-measures/2025-09-01.json` | 核查规则库（办法） | 生成器产出（条号已核） | 自制（条款以"条号+要点"呈现，不转载全文） | ✅ M2（9 条：**2 verified**（第四条第二款导出、第六条传播提示）+ 7 pending（与国标同 target）） |
| `data/rules/gb45438-2025/2025-09-01.json` | 核查规则库（强标） | 生成器产出（**逐页核对原文**） | 自制（条款以"条号+要点"呈现；标准全文不转载） | ✅ M2（25 条全 verified，含 M2 新增 §6.1 c) 唯一性规则） |
| `data/mapping/national-fields.json` | 元数据字段映射表 | 生成器产出（依 GB 45438-2025 §6.1 + 附录 E） | 自制 | ✅ M2（5 字段全 verified + **解析画像** `parse_profile`） |
| `data/knowledge/raw/labeling-measures/2025-09-01-fulltext.txt` | 依据原文快照（办法全文） | 中国政府网（curl 落盘提取正文） | 行政性质官方文件（著作权法第五条，不适用版权保护） | ✅ M1 |
| `data/knowledge/raw/gb45438-2025/2025-09-01-verification.md` | 依据核对记录（标准） | openstd.samr.gov.cn 在线预览逐页核对 | 仅登记元数据 + 条号要点对照，**不转载标准全文** | ✅ M1 |
| `data/knowledge/raw/related-regulations/deep-synthesis-provisions.txt` | 上位规章全文快照 | 中国政府网（curl 落盘提取正文） | 行政性质官方文件（著作权法第五条） | ✅ M1（**M2 定夺：显式不纳入判定路径**，仅参考） |
| `data/knowledge/raw/related-regulations/generative-ai-interim-measures.txt` | 上位规章全文快照 | 中国政府网（curl 落盘提取正文） | 行政性质官方文件（著作权法第五条） | ✅ M1（同上） |
| `data/truth/index.json` + `case-*.json` | 合成样本真值库 | 生成器产出（`tools/gen_samples.py`，固定 seed） | 自制（完全虚构内容） | ✅ M1（8 例；**M4 由内置基准消费，未另造一套**） |
| `data/parse/fixtures.json` | **解析通路算例**（真实容器字节 + 植入真值） | 生成器产出（`tools/gen_parse.py`，确定性字节构造） | 自制（完全虚构内容；字节为程序构造的最小合法容器） | ✅ **M2**（11 例，覆盖 PNG/JPEG/ISO BMFF） |
| `data/samples/card-*.json` | 示例标识卡（演示用） | 生成器产出（`tools/gen_samples.py`） | 自制（MIT） | ✅ M1（随生成器刷新） |

> **M3 无新增冻结数据资产**：批量扫描与对账的输入是**用户目录/清单**（不随仓发布），
> 报告产物由调用方指定输出目录（不进仓）。M3 的验证靠 `tests/test_scan*.py` /
> `tests/test_report.py` / `tests/test_evidence.py` 在**临时目录**构造算例（不新增入库数据）。

> **M4 无新增冻结数据资产**：内置基准**消费既有真值**（`data/truth/` 8 例 + `data/parse/fixtures.json`
> 11 例），另按 `check_type`/注入类型**程序化扩展**算例（合规取值/枚举**从规则库派生**，不落盘）；
> 引擎分支类用例（未映射字段 → `unknown`、无适用规则 → `not_assessed`）在**临时合成数据目录**跑，
> 跑完即删——仓库 `data/` 与 `tests/` 均不新增文件。M4 的验证靠 `tests/test_benchmark_*.py`
> 与 CLI `bench`（仓库真实数据下三类基准必须全部达标）。

> **M5 无新增冻结数据资产**：桌面界面与打包**消费既有数据**（规则库/映射表/真值库/解析算例/样本/
> 依据快照），`packaging.DATA_SUBDIRS` 白名单就是这些目录；演示素材
> （`docs/demo/*.png`、`demo.gif`）由 `tools/make_demo_assets.py` **离屏渲染真实界面**产出，
> 属**可再生的展示资产**（非冻结数据、不做位级守门），不入 `data/`。
> `data/**/_private/`（本地私有件）已在 `.gitignore`，且**不在**打包白名单内（不进发行包）。

### 1.1 生成器指纹（sha256，重生成须一致）

| 产物 | sha256 |
|---|---|
| `data/rules/labeling-measures/2025-09-01.json` | 见 `registry.json` 登记值（`--check` 守门） |
| `data/rules/gb45438-2025/2025-09-01.json` | 见 `registry.json` 登记值（`--check` 守门） |
| `data/mapping/national-fields.json` | 由 `tools/gen_mapping.py --check` 守门 |
| `data/truth/**` + `data/samples/**` | 由 `tools/gen_samples.py --check` 守门 |
| `data/parse/fixtures.json` | 由 `tools/gen_parse.py --check` 守门 |

> **指纹口径**：规则文件的登记值与**加载器**算出的规范化指纹一致
> （`sha256_text(canonical_json(data, indent=None, sort_keys=True))`，见 `rules/loader.py`）；
> 不一致 → 加载器以 exit 3 拒绝（数据真伪门）。每次改数据须重跑生成器并同步 `registry.json`。

> **解析算例为何 base64**：`data/**` 为冻结文本资产（全仓 EOL 门要求零 CR），而 PNG/JPEG/MP4
> 二进制可能含 `0x0D` 字节 → 直接入仓会误触 EOL 门。base64 解码后仍是**真实容器字节**，
> 解析通路被完整执行（见 `tests/test_parse_regression.py`）。

## 二、依据查证记录（M1 逐条核对结果）

| # | 依据 | 官方来源渠道 | 核对结论（M1 实测 2026-10-13） |
|---|---|---|---|
| 1 | 《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号） | 中国政府网全文（`content_7014286.htm`） | ✅ 全文 14 条已入库快照；**第四条**显式标识（六项 + 导出要求）、**第五条**隐式标识（属性信息/服务提供者名称或编码/内容编号）、**第六条**传播平台义务——条号与要点已核，规则库条目已挂真实条号 |
| 2 | GB 45438-2025《网络安全技术 人工智能生成合成内容标识方法》 | openstd.samr.gov.cn 在线预览（hcno=F32EA2A561F1886CD8D606513512D547） | ✅ **19 页预览逐页核对**：显式位置取值（文本/音频/视频=起始·末尾·中间；图片=边或角）、隐式要素清单（§6.1 a) 1)–5)）、**规范性附录 E** 元数据格式（AIGC 字段 + Label 取值 1/2/3 + 全字符串类型）全部落库，22 条规则已挂条号转 verified |
| 3 | 《互联网信息服务深度合成管理规定》 | 中国政府网全文（`2022-12-12/content_5731431.htm`） | ✅ 全文快照入库（网信办/工信部/公安部令第 12 号；**第十六条**添加标识、**第十七条**显著标识——正是《标识办法》第四条/第五条引用的上位条款）；首期作"参考依据"，不入判定路径（`plan/06` P1 收尾前定夺） |
| 4 | 《生成式人工智能服务管理暂行办法》 | 中国政府网全文（`202307/content_6891752.htm`） | ✅ 全文快照入库（**第十二条**要求按深度合成规定对图片/视频等生成内容标识）；同上，首期作参考依据 |

> ⚠️ **V5 时效性结论（写法保留）**：截至 **2026-10-13**，在 openstd 标准目录（关键词"人工智能生成合成内容标识"与"45438"）与 gov.cn 政策文件库（关键词"人工智能生成合成内容标识办法"）**均未见** GB 45438-2025 的替代/新增配套国标或办法修订。
> 中文通用检索受限，**不能以"未搜到"证否**——结论仅记"所列渠道未见"。

### 2.1 核对中的实测发现（写进记录，不擅自调和）

| 发现 | 处理 |
|---|---|
| GB 45438-2025 **附录 E（规范性）** 隐式键名写作 `ContentPropagator` / `PropagateID`，而**附录 F（资料性）** 示例写作 `Propagator` / `PropagatorID` | 映射表**两套键名同时登记别名**（不在数据层"二选一"，避免把标准自身表述差异固化成判定口径） |
| M0 骨架把隐式"服务提供者"拆成 `service_provider_name` + `service_provider_code` 两个字段 | **修正为单一字段 `content_producer`**——标准 §6.1 a) 2) 与附录 E d) 定义为单要素"名称**或**编码" |
| 标准 §5.x 显式要求含"人工智能/AI"与"生成/合成"两要素 | 建为 `pattern` 规则（`ai_element` / `gen_element`），位置另建 `position` 规则 |
| 《标识办法》第四条–第六条技术判定与国标 §5/§6 同源 | 办法条目记录法定义务与真实条号，**保持 pending**（技术判定由国标承担，避免同 target 跨文档双份 Finding）；**M2 例外**：办法独有义务（第四条第二款导出文件、第六条传播平台提示）有独立 target 与明确场景门控，已转 verified |

### 2.2 M2 适用性画像与建条决策

| 事项 | 处置 | 依据 |
|---|---|---|
| 传播要素（§6.1 a) 4) 5)）M1 时 pending | **M2 转 verified**，带 `only_if.scenario=[propagated]` | 办法第六条（传播平台义务）+ 适用性画像 |
| 办法第四条第二款（导出文件显式标识） | **新增 verified 规则**，`only_if.scenario=[exported]` | 办法第四条第二款 |
| 办法第六条（发布内容周边提示） | **新增 verified 规则**，`only_if.scenario=[propagated]` | 办法第六条 |
| §6.1 c)「仅保留一份文件元数据隐式标识」 | **新增 verified `unique` 规则** | 国标 §6.1 c) |
| 附录 E 预留字段（ReservedCode1/2） | **不建规则**：标准未定义语义与取值 | 不编造义务（plan/06 D27） |
| §5.x 数值量阈值（字号/时长/语速等） | **不建规则**：M1 核对记录未覆盖任何数值量 | 不编造数值（plan/06 D27） |
| 上位规章（深度合成规定/生成式 AI 办法） | **显式不纳入判定路径** | 判定要素已被办法 + 国标覆盖（plan/06 P1 结论） |

> **场景门控语义**：规则 `only_if.scenario` 未命中 → 引擎记 `skipped`（**不是 fail**）：
> 把"不适用"判成违规是冤枉用户。`skipped` 不参与分级；若一条规则都不适用 → 等级 `not_assessed`。

## 三、合成数据纪律

- **合成样本**：全部由 `tools/gen_samples.py` 构造，内容为**完全虚构**占位内容——服务提供者编码用 `SYN-*`、内容编号用 `SYN-C######`，**不收录任何真实平台内容/真实用户信息/真实商业素材**（守门测试 `test_samples_are_fully_fictional`）。
- **解析算例**：由 `tools/gen_parse.py` 构造**最小合法容器字节**（PNG/JPEG/ISO BMFF），载荷内容同样全部虚构（`SYN-*`），
  仅用于验证解析通路与降级行为；字节由固定常量构造（无真实媒体数据）。
- **植入真值**：每例输出 `{input_card, expected}`；`expected` 声明主期望 `grade` 与 `also_expect`（非 pass 目标集）。真值库**已与引擎输出全量对账一致**（`tests/test_generators.py::test_truth_library_reconciles_with_engine`）。
- **解析真值**：`data/parse/fixtures.json` 每例声明解析可观测性 + 核验结论，**已与"解析 → 核验"全链路对账一致**（`tests/test_parse_regression.py`）。
- **缺陷覆盖**：标识卡算例覆盖 `correct / missing_field / wrong_position / wrong_value / bad_format / metadata_stripped / explicit_only` 七类（另加图片位置越界一例）；解析算例另覆盖 `structure_broken / duplicate_label`（边界情形"元数据被剥离但显式标识在"两类均有）。
- **可复现**：生成器固定 `seed=45438`（解析算例为确定性字节构造）；`--check` 守门断言"再生成位级一致"；产物无时间戳、LF 落盘。

## 四、法律与许可口径

- 规则库 JSON 中的条款信息以"文号/标准号 + 条号 + 要点"形式呈现（**规避全文转载**）；
- `data/knowledge/raw/labeling-measures/` 为**行政性质官方公文**（著作权法第五条不适用版权保护）；
- `data/knowledge/raw/gb45438-2025/` 仅登记**书目元数据 + 条号要点对照 + 逐页核对记录**，**不转载受版权保护的标准全文**（全文以官方在线预览为准）；
- 合成样本与真值库为本项目自制，MIT 许可随仓库发布。

## 五、重生成命令

```bash
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py     # 规则库 + registry sha256
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_mapping.py      # 字段映射表（含解析画像）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_samples.py      # 真值库 + 示例卡
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_parse.py        # 解析通路算例（真实容器字节）
# 四者的 --check 均断言"与已入库产物逐字节一致"（CI/守门测试调用）
```

## 六、解析通路算例（M2）

`data/parse/fixtures.json` 是**解析通路回归**的算例集：每例含 `bytes_b64`（**真实容器字节**的
base64）与 `expected`（解析可观测性 + 核验结论）。回归链路：

```
bytes_b64 → base64 解码 → labelcheck.parse.parse_bytes（容器结构解析 + AIGC 载荷抽取）
          → labelcheck.engine.check_card（同一判定路径）
          → 与 expected 对账（tests/test_parse_regression.py）
```

覆盖形态见 §三；容器覆盖 PNG / JPEG / ISO BMFF（MP4/M4A），载体覆盖 image / video / audio。
**降级算例**（结构截断、无载荷）与**正常算例**并存，确保"未观测 → 不给假结论"的路径被真跑覆盖。
