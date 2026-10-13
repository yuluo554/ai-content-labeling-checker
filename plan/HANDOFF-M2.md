# HANDOFF-M2：M1 → M2 交接快照

> **用法**：新对话读 `plan/HANDOFF-M2.md` 继续完成任务（会话启动命令给绝对路径即可）。
> **上一棒**：M1 数据先行（规则库逐条挂原文核对 + 字段映射表 + 合成样本真值库 + 台账）✅ 完成 2026-10-13。
> **下一棒**：M2 显式/隐式核验引擎充实（真实规则驱动）+ 解析通路首批载体 + 算例回归 100%。

---

## 一、M1 交付物（已落地，勿重复造）

**依据核对（M1 主任务，已完成）**

| 依据 | 核对方式 | 结果 |
|---|---|---|
| 《标识办法》国信办通字〔2025〕2 号 | 中国政府网全文 `content_7014286.htm` → 快照落库 | 14 条全文入库；第四/五/六条条号核对完成 |
| GB 45438-2025 强标 | openstd 在线预览 **19 页逐页核对**（hcno=F32EA2A561F1886CD8D606513512D547） | 显式 §5.1–5.4 + 隐式 §6.1 + **规范性附录 E** 全部核对完成 |

落库位置：
- `data/knowledge/raw/labeling-measures/2025-09-01-fulltext.txt`（办法全文 + 出处头）
- `data/knowledge/raw/gb45438-2025/2025-09-01-verification.md`（书目元数据 + 逐页核对记录 + 取值来源对照 + V5 时效性结论）
- `data/knowledge/raw/related-regulations/`（**上位规章全文快照**：深度合成规定、生成式 AI 办法；首期作参考依据，不入判定路径）

**规则库（生成器产出，22 条生效）**

- `data/rules/gb45438-2025/2025-09-01.json`：共 24 条，其中 **22 条 `verified`**（16 条显式 = 4 载体 ×
  {presence, position, ai_element, gen_element}；6 条隐式）+ 2 条传播要素 `pending`（适用性画像 M2）；
- `data/rules/labeling-measures/2025-09-01.json`：9 条**全 `pending`**（记录法定义务 + 真实条号，判定路径由国标承担）；
- 隐式规则覆盖（6 条 verified）：`content_property`（presence critical + enum minor）、`content_producer`
  （presence major + type minor）、`content_id`（presence minor + type minor）。

**字段映射表**：`data/mapping/national-fields.json`，**5 字段全 `verified`**（content_property / content_producer / content_id / content_propagator / propagate_id）。

**真值库**：`data/truth/`（`index.json` + 8 例 `case-*.json`），与引擎**全量对账一致**；覆盖 plan/05 §三.3 全部 7 类缺陷 + 图片位置越界一例。

**生成器**：`tools/gen_rulesets.py`、`tools/gen_mapping.py`、`tools/gen_samples.py`（均支持 `--check`）。

**测试**：**174 项全绿**（Python 3.8.8 与 3.12 双通过）；新增 `tests/test_generators.py`（生成器位级一致 + 真值对账 + 缺陷枚举覆盖 + 样本全虚构）。

## 二、M1 关键口径变化（**与本 HANDOFF 同步的既定口径，改前先对照**）

| 变化 | 内容 | 影响面 |
|---|---|---|
| **隐式字段合并** | `service_provider_name` + `service_provider_code` → **单一字段 `content_producer`**（标准 §6.1 a) 2) 定义为"名称**或**编码"） | 映射表、隐式规则、真值库 |
| **显式要素 id** | 统一为 `<carrier>_explicit_notice`（text/image/audio/video） | 规则库 target、标识卡 explicit[].element |
| **位置枚举取值** | text/audio/video = `head`/`tail`/`middle`；image = `edge`/`corner` | position 规则 `params.allowed` |
| **办法条目 pending** | 办法条目记录法定义务但不进判定（避免与国标同 target 双份 Finding） | 门控计数（生效 22 / 待核对 11） |
| **附录 E/F 键名并存** | 传播要素两套键名同时登记别名（`ContentPropagator`+`Propagator`；`PropagateID`+`PropagatorID`） | 映射表 aliases |
| **文档 status 一致性守门** | 有 verified 条目的文档必须 `status=verified`（否则双重门控静默失效） | `test_guard_data.py` |

## 三、M2 待办（下一棒）

1. **解析通路首批载体接入**（plan/06 P2 定夺）：把"标识卡 JSON（UMR）"之外的**可解析载体**接入——
   优先 **图片容器元数据**（JPEG/PNG 的 EXIF/XMP → AIGC 字段，附录 F.1 示例结构）；
   音视频（F.2/F.3 的 M4A/MP4 元数据）次之。解析失败**显式降级 `unknown`**（不臆测）。
2. **载体适用性画像**：实现办法第四条第二款（导出文件含显式标识）与第六条（传播平台提示）的
   **适用性判定**，据此决定 3 条 `pending` 条目（2 条传播要素 + 1 条办法导出规则）能否转 verified。
   这是把 pending 转 verified 的**唯一正当路径**（先有适用性画像，再核对）。
3. **算例回归 100%**：把 `data/truth/` 从"引擎对账"扩到**解析通路回归**（真实容器文件 → 解析 → 核验 → 对账）。
4. **规则库扩充**：GB 附录 E 的**预留字段**（ReservedCode1/2）与 §6.1 c)（仅保留一份隐式标识）、
   §5.x 的**字高/时长/语速**数值约束（5%、2s、120–160 字/min）——按 necessity 决定是否建规则。
5. **上位规章（V4）**：`plan/06` P1 收尾前须给结论（纳入判定 or 显式不纳入）；首期作参考依据。

## 四、关键命令速查

```bash
# 生成器（改数据唯一路径；--check 断言位级一致）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py && py -X utf8 tools/gen_mapping.py && py -X utf8 tools/gen_samples.py
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py --check

# 数据与自检
PYTHONPATH=src py -X utf8 -m labelcheck selfcheck
PYTHONPATH=src py -X utf8 -m labelcheck version

# 单件核验（M1 后为实际判定）
PYTHONPATH=src py -X utf8 -m labelcheck check data/samples/card-text-basic.json -v            # compliant, exit 0
PYTHONPATH=src py -X utf8 -m labelcheck check data/samples/card-image-metadata-stripped.json  # non_compliant, exit 1

# 测试（两版本）
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -X utf8 -m pytest tests/ -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest tests/ -q

# 生效规则数（M1 后应为 22）
PYTHONPATH=src py -X utf8 -c "from labelcheck.paths import find_data_dir; from labelcheck.rules import effective_ruleset; r=effective_ruleset(find_data_dir()); print(r.verified_rule_count, r.pending_rule_count, r.coordinate)"
```

## 五、本机环境事实与坑（沿用 M0，仅列实测）

- 解释器：`py -0p` → **3.8.8** 与 **3.12**；Windows 上 `python` 是商店占位符，**一律用 `py`**；命令加 `-X utf8`。
- **Python 3.8 无 `Path.write_text(newline=)`**——写 LF 必须 `open(..., newline="\n")`（M1 实测踩过）。
- **Git Bash 的 `/tmp` 与 Windows Python 不互通**：临时文件用工作区相对路径或 Python `tempfile`（M1 实测踩过）。
- 抓官方页面：`curl -s -L --max-time 40 <url> -H "User-Agent: Mozilla/5.0"`；字符集按页面声明解码（gov.cn 为 utf-8）。
- openstd 标准全文预览是**逐页图像 + 10×10 CSS 瓦片拼图**（console-ban）；直接取 `viewGbImg?fileName=<bg>` 得 WebP 图块，
  按页内 `pdfImg-<x>-<y>` 的 `background-position` 拼回整页（M1 用此方式核对）。**图像不留仓**（标准受版权保护）。
- 全项目测试**单次 <2 秒**，无需分批；跨平台结论**以 CI 为准，别拿本机全绿当证据**。

## 六、M1 DoD 逐项核对（已闭合）

- [x] `data/knowledge/raw/` 原文快照入库（办法全文 + 国标逐页核对记录），台账挂 URL + 抓取日期
- [x] GB 45438-2025 隐式字段清单逐条核对完成，条目 `status=verified` 且挂条号（§6.1 a) 1)–5) + 附录 E）
- [x] 显式标识位置/形式要求逐条核对完成，位置枚举值可溯（§5.1–5.4）
- [x] `tools/gen_rulesets.py` 跑通产出冻结规则库；registry sha256 同步（篡改实测 → exit 3）
- [x] `data/mapping/national-fields.json` 建表（别名 + status + 出处；口径修正为 `content_producer`）
- [x] `tools/gen_samples.py` 产出合成样本 + 真值（固定 seed，位级一致守门通过）
- [x] `data/README.md` 台账登记全部资产（来源/许可/指纹）
- [x] 测试全绿（174 项，3.8/3.12）+ `effective_ruleset()` 首次非空（22 条）

**偏差说明**：V4（上位规章条文）未入库，首期作参考依据、不入判定路径（`plan/06` P1 收尾前定夺）——
非 M1 范围内阻塞项，已在计划中标明。其余无偏差。

## 七、留给 M6（发布）的必办项（**勿忘**）

1. **提交元数据邮箱是真实个人邮箱**（`git log --format="%ae %ce"` 可见）——发布前须用
   `filter-branch --env-filter` 全历史改写为 GitHub noreply，并同步 `git config user.email`。
   **历史重写属对外结构性动作，须用户明确授权**后再做（skill 阶段 7）。
2. **脱敏扫描的已知假阳性**：示例标识卡里的假 sha256 hex 串（64 个连续 hex 字符）会命中"18 位身份证"
   正则。M6 审计脚本须给 phone/idcard 模式加 **hex 边界环视** `(?<![0-9a-fA-F])…(?![0-9a-fA-F])`，
   并把该形态写进 selftest 阴性对照。
3. **`data/knowledge/raw/` 的版权口径**：办法全文为行政公文（可留档）；国标**不转载全文**，
   只留书目元数据 + 条号要点对照（已按此办理，M6 复核一遍）。
4. `data/**/_private/` 已在 `.gitignore`（M0 补齐），M6 复核。
