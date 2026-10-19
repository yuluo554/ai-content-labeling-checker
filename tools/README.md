# tools/ 生成器与运维脚本

> 纪律（plan/05 §二/§三）：数据资产由**生成器**产出，**禁手改**产物；生成器必须确定性
> （固定 seed → 任意机器逐字节一致）。

| 脚本 | 作用 | 里程碑 | 状态 |
|---|---|---|---|
| `gen_rulesets.py` | 从确定性模板生成 `data/rules/<doc>/<ver>.json` 冻结规则库，回填 `registry.json` 的 sha256 | M1（M2 扩充场景门控 + unique） | ✅ 已实现 |
| `gen_mapping.py` | 生成 `data/mapping/national-fields.json`（依 GB 45438-2025 §6.1 + 附录 E + 解析画像） | M1（M2 加 `parse_profile`） | ✅ 已实现 |
| `gen_samples.py` | 构造合成样本 + 植入真值（`labelcheck.rng` 确定性 RNG，固定 seed） | M1 | ✅ 已实现 |
| `gen_parse.py` | 构造**真实容器字节**（PNG/JPEG/ISO BMFF）解析算例 + 植入真值（确定性字节构造） | **M2** | ✅ 已实现 |
| `make_demo_assets.py` | 离屏渲染 GUI 页签 → `docs/demo/` 截图 + GIF（需 PySide6，惰性导入） | **M5** | ✅ 已实现 |
| `build_exe.py` | 构建 PyInstaller onedir 双 exe（GUI + CLI）+ 构建后自动校验 | **M5** | ✅ 已实现 |
| `verify_package.py` | 冻结态包验收（中立环境 + 清环境变量 + 断言数据目录落在 dist 之内） | **M5** | ✅ 已实现 |
| `labelcheck.spec` | PyInstaller 规格（双 exe；数据白名单内嵌；CLI 排除 Qt） | **M5** | ✅ 已实现 |
| `entry_gui.py` / `entry_cli.py` | 双 exe 的入口脚本（GUI 支持 `--selftest` 写文件自检） | **M5** | ✅ 已实现 |
| `audit_desensitize.py` | 脱敏四步审计（发布门）：内容扫描 + 提交邮箱 + 资产口径 + 版权口径；含探测器阳性/阴性对照自检 | **M6** | ✅ 已实现 |

## 用法（M1/M2 生成器）

四个生成器都支持 `--check`：**比对已入库产物与重生成结果，不一致即非零退出**
（`tests/test_generators.py` 与 `tests/test_parse_regression.py` 以子进程调用它，
构成"再生成位级一致"守门）。

```bash
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py            # 生成规则库 + registry
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py --check    # 校验位级一致
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_mapping.py             # 生成字段映射表
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_samples.py             # 生成真值库 + 示例卡
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_parse.py               # 生成解析通路算例
```

**改数据的唯一路径**：改模板（`gen_*.py`）→ 重跑生成器 → 重跑测试。
**禁手改** `data/rules/**`、`data/mapping/**`、`data/truth/**`、`data/samples/**`、`data/parse/**`（会被 `--check` 抓出）。

> **`gen_parse.py` 的构造器复用**：`png_bytes` / `jpeg_bytes` / `mp4_bytes` / `aigc_json` 同时被
> `tests/test_parse.py` 导入（测试**现造字节**，不读仓库数据）——保证测试与算例产出**同源**，
> 不会出现"测试用的是另一套容器构造"的漂移。

> 生成器通过 `sys.path` 注入 `src/` 复用 `labelcheck.jsonio`（LF 落盘 / 规范化 JSON /
> `sha256_text`），使产物指纹与**加载器**校验口径完全同源——这是"填了 sha256 就必须一致"的前提。
> `gen_parse.py` 亦从 `gen_mapping` 导入 `PARSE_PROFILE`（载荷外层包裹键的**单一事实源**）。

## 用法（M5 打包与演示素材）

```bash
# 构建免安装双 exe（GUI 窗口版 + CLI 控制台版）+ 构建后自动校验
py -3.12 -X utf8 tools/build_exe.py --clean

# 冻结态包验收（中立环境：清 LABELCHECK_DATA_DIR、以 exe 目录为 CWD）
py -3.12 -X utf8 tools/verify_package.py
py -3.12 -X utf8 tools/verify_package.py --json     # CI 用

# 生成 README 演示素材（离屏渲染真实界面；需 gui extra）
py -3.12 -X utf8 tools/make_demo_assets.py
py -3.12 -X utf8 tools/make_demo_assets.py --check  # 只校验素材存在
```

**为什么"构建"与"验收"分开、且验收必须中立**：数据目录定位有四个分支，其中"环境变量"与
"CWD 上溯"都能兜底命中**仓库** `data/`。若沿用当前环境或从仓库根跑自检，冻结态自检会命中仓库
数据——exe 在本机看着能跑、换台机器就崩（系列实测假结果陷阱）。故 `verify_package.py`
必须：① 清 `LABELCHECK_DATA_DIR`；② 以 exe 目录为 CWD；③ 断言解析到的数据目录**落在 dist 之内**。

**产物**：`dist/labelcheck-gui/labelcheck-gui.exe`（`console=False`，双击即用）与
`dist/labelcheck/labelcheck.exe`（`console=True`，可管道取 JSON、判退出码）。CLI exe
**排除 PySide6/PIL/numpy**（保住"零 GUI 依赖"与体积：实测 GUI ≈158 MB / CLI ≈13 MB）。
`dist/`、`build/`、`*.spec` 的产物均在 `.gitignore` 内，**不入仓**。

> **GUI exe 的自检方式**：窗口版 stdout 不接终端，故 `tools/entry_gui.py` 支持
> `--selftest <file>`——把装配结果（页签数、数据目录、生效规则数）写进 JSON 文件并以退出码
> 报告成败，供无显示环境下脚本化验收。

## 用法（M6 脱敏审计，发布门）

```bash
# 四步一次跑全（内容扫描 + 提交邮箱 + 资产口径 + 版权口径）
py -X utf8 tools/audit_desensitize.py
py -X utf8 tools/audit_desensitize.py --json      # 机器可读（CI 用）
py -X utf8 tools/audit_desensitize.py --strict    # 把"提交邮箱待改写"也算不通过（发布前最终门）
py -X utf8 tools/audit_desensitize.py --emails    # 只看提交元数据邮箱
py -X utf8 tools/audit_desensitize.py --selftest  # 探测器阳性/阴性对照（自证非空验）
```

退出码：`0` 无阻断项 / `1` 有阻断项 / `2` 用法错误。

**四步与判定口径**（对应 plan/HANDOFF-M6.md §三.1）：

1. **内容扫描**：按 `git ls-files`（含未跟踪未忽略者）遍历**文本**文件，用一组正则探测
   邮箱 / 真实用户路径 / 手机号 / 身份证 / 私钥 / 令牌 / UNC / 内网 IP / 长 hex。
   **手机号与身份证必须带 hex 边界环视** `(?<![0-9a-fA-F])…(?![0-9a-fA-F])`——否则示例卡里
   的假 sha256 会命中"18 位身份证"正则（M0–M5 反复记录的已知假阳性）。长 hex（sha256 指纹）
   定级 **advisory**（只报不阻断）：内容指纹是本项目的文档化功能。
2. **提交元数据邮箱**：`git log --format="%ae|%ce"` 读出全历史作者/提交者邮箱；非 GitHub
   noreply 者列出并给出处置。**历史重写属对外结构性动作，须用户明确授权**，故该项默认
   **advisory**（不阻断退出码），`--strict` 下阻断。
3. **资产口径**：`.gitattributes` 必须 `text=auto`+`eol=lf`；`data/parse/fixtures.json` 必须
   列入白名单且无 CR；`.gitignore` 含 `data/**/_private/` 与 `!tools/*.spec`；无被跟踪的
   `_private`/`dist`/`build` 文件。
4. **版权口径**：`data/knowledge/raw/gb45438-2025/` 只留书目元数据 + 核对记录（**不转载标准
   全文**，记录须含"不转载"声明）；办法全文为行政公文可留档。

**放行机制**：白名单路径（`data/parse/fixtures.json`、`data/knowledge/raw/**`）与
**行内标记** `audit-allow`（命中所在行含该标记）都把命中转为"白名单放过"——仍在输出可见，
只是不计入阻断，供刻意构造的样本/夹具使用（工具自检与测试夹具即靠它自证不误伤）。

> **自检为什么重要**：没有阳性/阴性对照，探测器可能是**空验**（一个都匹配不到，看着"全绿"）。
> `--selftest` 同时断言"真手机号/身份证必须命中"与"含长数字串的假 sha256 不得误报"，
> 并直接钉死"朴素正则确实会误报、带环视不会"这一对照前提。
