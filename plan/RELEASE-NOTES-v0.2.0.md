# labelcheck v0.2.0

**AI 生成合成内容标识合规核查器**——以《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号，
2025-09-01 施行）与强制性国家标准 **GB 45438-2025**《网络安全技术 人工智能生成合成内容标识方法》
为规则源，把**显式标识 + 隐式元数据标识**的合规核验做成**规则化、可批量、留指纹证据**的本地工具
（桌面 exe + CLI 双形态）。**全本地核查、零上传**，不做任何去水印/标识规避。

> 技术报告见 [docs/技术报告.md](https://github.com/yuluo554/ai-content-labeling-checker/blob/main/docs/技术报告.md)。

## 下载即用（免安装）

| 产物 | 形态 | 用途 |
|---|---|---|
| `labelcheck-gui-v0.2.0-win64.zip` | 窗口版（无控制台） | 解压后双击 `labelcheck-gui.exe` |
| `labelcheck-cli-v0.2.0-win64.zip` | 控制台版 | 脚本化 / 无 GUI 机器（可管道取 JSON、判退出码） |

解压到任意目录即可运行（onedir 形态，无需安装 Python）。

**校验（sha256）**：

| 附件 | 大小（字节） | sha256 |
|---|---|---|
| `labelcheck-cli-v0.2.0-win64.zip` | 8707964 | `3f8255c9e8e3ab5450b7f8de94550ec4588846b9030aab00b75d243f0ad9da7b` |
| `labelcheck-gui-v0.2.0-win64.zip` | 49977434 | `1c44785b9335c7c3eb94f47a6908354008c4c536e0681a4ee2f0051eb1504467` |

```powershell
certutil -hashfile labelcheck-cli-v0.2.0-win64.zip SHA256
certutil -hashfile labelcheck-gui-v0.2.0-win64.zip SHA256
```

> 两个 zip 均经**解压后中立环境自检**验证（CLI 用 `selfcheck`、GUI 用 `--selftest`：
> `frozen=true`、数据目录落在解压目录内、生效规则 27 条、六页签）。

## v0.2.0 新增

**1. SARIF 2.1.0 导出（`scan --sarif FILE`）**

可直接接进代码扫描 / 缺陷跟踪平台。语义上**只搬运既有判定**，不新增结论：

- `fail` → `level` 由既有 `severity` 固定映射（critical→error / major→warning / minor→note）；
- `unknown` → 保留为 `level=note` + `properties.status=unknown`
  （本工具的既定口径是"未观测/缺值 ≠ 合规"，从导出里抹掉它等于制造假合规）；
- `skipped`（当前场景不适用）**不导出**；
- 失败件（读取/解析失败）单列为 `ruleId=scan_error`，不静默消失。

**2. 单文件 HTML 报告（`scan --html FILE`）**

内联样式、**零 JS、零外链**——打开报告不产生任何联网（与本工具"全本地、零上传"一致）。
段落与 Markdown 报告对齐，强制免责声明保留，输入值全部转义。

**3. `rules` 只读子命令**

```bash
labelcheck rules                                  # 条目（缺省连 pending 一起列）
labelcheck rules --scope implicit --status verified
labelcheck rules --mapping --json                 # 含字段映射表，机器可读
```

把"规则库里到底有哪些条目、哪条还没核对、字段别名怎么映射"变成一次命令，而不是去翻 JSON。
纯只读：不判定、不写盘。

> 两项导出都是**旁路**：默认报告包（`report.md` / `summary.csv` / `detail.csv` /
> `report.xlsx` / `evidence.json`）的字节与 `evidence.json` 里的报告指纹**一字未改**。

## v0.2.0 工程加固

- **Python 下限 3.8 → 3.12**：3.8 已于 2024-10-07 EOL。旧解释器只在 Windows 守的口径取消，
  CI 改为 `windows×3.12` + `ubuntu×3.12`。
- **PySide6 6.12 / PyInstaller 6.22**：旧上限（`<6.8`）无实测理由，已放开；3.8 的 marker 分支全删。
- **CI 覆盖补齐**：
  - test job 安装 `report` extra —— 修前 CI 从不装 openpyxl，**XLSX 确定性测试每次都 skip**
    （"有测试"实际是"从未验证过"）；
  - 每个跑 pytest 的 job 增加**收集数对账**（test=449 / gui-smoke=465 / packaging-guard=18），
    写死期望值，防"少收集也绿"；
  - 新增 **`package` job**：真跑 `build_exe --clean` + `verify_package.py`，
    让"发布物可复现"从本地纪律变成常驻门禁；
  - actions 升 `checkout@v7` / `setup-python@v7`（v4/v5 已收 Node.js 20 弃用警告）。
- **修掉 4 处真实缺陷**（首轮 CI 暴露，均为既有代码在现代化后显形）：
  1. GUI 页签测试 16 项**全过**却让 pytest 退出码非 0（Qt 6.12 下未关闭窗口在解释器退出期 abort）；
  2. `build_exe.py` 在 Windows runner（cp1252 stdout）上构建前就崩；
  3. `verify_package.py` 验收全过后在最后一行中文输出上崩；
  4. tools 共享模块在 `python -m tools.*` 下不可导入。
  这四条现在都有测试锁住，不会悄悄回来。

## 判定行为未变

本轮不改规则条目、不改 `status` 分布（**27 生效 / 7 待核对**）、不改引擎判定与分级、
不改三类基准阈值与真值、不改退出码语义 `0/1/2/3`：

| 基准 | 指标 | 结果 | 要求 |
|---|---|---|---|
| `fields` | 判定准确率 | **100%**（30/30） | 100% |
| `constructed` | 检出率 | **100%**（23/23） | ≥ 95% |
| `constructed` | 误报率 | **0%**（0/11） | 0（硬口径） |
| `diff` | 对账集合一致率 | **100%**（2/2） | 100% |

退出码实测：合规卡 `0` / 剥离卡 `1` / 坏路径 `2` / 坏 `LABELCHECK_DATA_DIR` `3` / `bench` `0`。

## 能做什么

- **单件核验**：显式标识**要素级 + 位置级**判定 + 隐式元数据字段级核验，结论逐条挂条款依据；
- **容器解析通路**：PNG / JPEG / MP4 / M4A 的元数据里抽取 AIGC 载荷（GB 45438-2025 附录 E 格式）
  → 同一标识卡；解析不到**显式降级**，绝不臆测；
- **批量扫描**：目录递归 / 清单投喂，失败件隔离（"未判定" ≠ "违规"）；超大容器安全阀；
- **两轮对账**：新增违规 / 已修复 / 持续违规 / 内容变动（**稳定身份键**配对，非内容指纹）；
- **报告与证据链**：Markdown / CSV / XLSX（可选）+ 每件内容指纹 + 报告自身 sha256；
- **内置评测基准**：三类，零 API、可重复，CI 每次重算防回退；
- **桌面界面**：六页签，只渲染引擎结果、零判定逻辑。

## 升级提示

- 本版要求 **Python 3.12+**；3.8–3.11 用户请留在 v0.1.0 或先升级解释器。
- `data/rules/registry.json` 新增 `next_review` 字段（下次复核 **2027-01-31**）；
  规则文件本身字节未变，旧数据目录仍可加载。

## 验证记录

- 本地 py3.12：**465 passed**（含 GUI offscreen + XLSX 真跑 + 真 exe 实跑），退出码 0；
- CI run [39258352167](https://github.com/yuluo554/ai-content-labeling-checker/actions/runs/39258352167)：
  **8 job 全 success**（test×2 / cli-smoke×2 / gui-smoke / packaging-guard×2 / package）；
- 发布物本体：`gh release download` 后核 sha256 → 解压中立目录 → `verify_package --dist` 退出 0。

**免责声明**：本核查结论供参考，正式合规认定以监管口径为准；本工具为合规辅助，
**不提供任何标识规避功能**。
