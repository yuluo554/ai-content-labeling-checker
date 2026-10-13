# RELEASE-M6：脱敏审计与发布留档

> **用途**：M6 发布门的**动作留痕**。四步脱敏审计的命令与结论、发布动作时序、待用户授权项，
> 全部如实记录在此（含"动作先于修正发生"这类瑕疵，事后补记录、不回填时间线）。
> 上游：[HANDOFF-M6.md](HANDOFF-M6.md)。纪律：**确认类条目只能在用户实际确认后打勾，禁止预填**。

---

## 一、脱敏四步审计（+ 产物本体扫描）

**工具**：`tools/audit_desensitize.py`（M6 新建，入仓可复跑）。退出码 `0` 无阻断 / `1` 有阻断 / `2` 用法错误。

```bash
py -X utf8 tools/audit_desensitize.py            # 四步 + 产物扫描
py -X utf8 tools/audit_desensitize.py --json     # 机器可读
py -X utf8 tools/audit_desensitize.py --strict   # 提交邮箱也计为不通过（发布前最终门）
py -X utf8 tools/audit_desensitize.py --selftest # 探测器阳性/阴性对照
```

### 1.1 探测器自检（`--selftest`）

| 项 | 内容 | 结论 |
|---|---|---|
| 阳性对照 | 10 条（邮箱 / 手机号 / 身份证 / 用户路径 / 私钥 / 令牌 / UNC / 内网 IP / 长 hex） | ✅ 全部命中 |
| 阴性对照 | 6 条（含长数字串的假 sha256 / YAML 行 / URL / 版本号 6.6.3.1 等） | ✅ 全部不误报 |
| hex 边界环视钉死 | 构造"含 18 位数字串的 64 位假 sha256"：**朴素正则命中、带环视的 phone/idcard 不命中** | ✅ 对照前提有效、环视生效 |

### 1.2 内容级扫描（步骤 2）

全量扫描 `git ls-files --cached --others --exclude-standard` 下的**文本**文件。

| 指标 | 值 |
|---|---|
| 扫描文本文件 | **113**（随 M6 新增文档增至该值；口径为 `git ls-files` 下全部文本文件） |
| 阻断项（block） | **0** |
| 白名单 / advisory 放过 | 35（规则库 sha256 指纹、真值库/示例卡 content_sha256、`data/parse/fixtures.json` base64 构造容器、官方依据快照、工具自检夹具的 `audit-allow` 行内标记） |

**命中分级口径**：`block`（真泄露：邮箱 / 手机号 / 身份证 / 真实用户路径 / 私钥 / 令牌 / UNC / 内网 IP）
与 `advisory`（长 hex 指纹——本项目**文档化功能**，只报不阻断）。手机号与身份证**必须带 hex 边界环视**
`(?<![0-9a-fA-F])…(?![0-9a-fA-F])`，否则示例卡的假 sha256 会误报（M0–M5 反复记录的已知假阳性）。

**本轮修正（内容级）**：`plan/HANDOFF-M1.md` 环境坑行原含**真实用户目录路径**（本机用户名）→
已改为描述性指代（"本机用户目录下的 `AppData\Local\Programs\Python\Python38`"），
命令 `git grep` 复扫 0 命中。

### 1.3 提交元数据邮箱（步骤 1）——**待用户授权**

| 项 | 值 |
|---|---|
| 提交数 | 5 |
| 作者/提交者邮箱（实测） | **真实个人邮箱 ×1**（QQ 邮箱；此处按脱敏纪律不复述字面值，仅记形态） |
| noreply 邮箱 | 无 |
| 处置 | `git filter-branch --env-filter`（或 `git-filter-repo`）全历史改写为 GitHub noreply，并同步 `git config user.email` |
| 授权状态 | ⬜ **待用户明确授权**（历史重写属对外结构性动作） |

> 本项默认 **advisory**（不阻断退出码），`--strict` 下阻断。**动作留档纪律**：改写执行后
> 在此补记时序（含"先扫描后修正"的顺序），**不复述敏感字面值**——留档本身须过扫描。

### 1.4 资产口径复核（步骤 3）

| 项 | 实测 | 结论 |
|---|---|---|
| `.gitattributes` | `text: auto` + `eol: lf`（`git check-attr` 实测） | ✅ |
| `data/parse/fixtures.json` | 在脱敏白名单内；无 CR（LF 文本资产） | ✅ |
| `.gitignore` `data/**/_private/` | 存在；无被跟踪的 `_private` 文件 | ✅ |
| `.gitignore` `!tools/*.spec` | 存在（构建脚本入仓例外） | ✅ |
| 被跟踪的 `dist/`/`build/` 文件 | 无（`git ls-files` 实测为空） | ✅ |

### 1.5 版权口径复核（步骤 4）

| 项 | 实测 | 结论 |
|---|---|---|
| `data/knowledge/raw/gb45438-2025/` | 仅 `2025-09-01-verification.md`（书目元数据 + 逐页核对记录，含"不转载"声明）；**无标准全文** | ✅ |
| `data/knowledge/raw/labeling-measures/` | 办法全文快照（行政公文，著作权法第五条） | ✅ 可留档 |

### 1.6 产物本体扫描（步骤 5，`--dist`）

内容级扫描证明"仓库树干净"，证明不了"冻结产物干净"——对 `dist/**` 做**字节读法**扫描。

| 项 | 实测 |
|---|---|
| 扫描产物文件 | **278** |
| 构建机路径 / 仓库名 / 私有目录混入 | **0** |
| 厂商串误报规避 | 只匹配组合路径签名（`10-13-ai-content-labeling-checker` / `ProgramData\` / 排除 `\Users\qt`），不匹配裸用户名——Qt DLL 等上游二进制的厂商串 0 误报 |

---

## 二、发布动作时序（**待用户授权**）

> **前置**：§1.3 的提交邮箱改写须先获用户授权并执行（否则推送即把真实邮箱带出）。

| # | 动作 | 命令（草案） | 状态 |
|---|---|---|---|
| 1 | 提交邮箱全历史改写（**须授权**） | `git filter-branch --env-filter …` + `git config user.email <noreply>` + `rm -rf .git/refs/original && git reflog expire --expire=now --all && git gc --prune=now --aggressive` | ⬜ 待授权 |
| 2 | 建远端仓库 | `gh repo create yuluo554/ai-content-labeling-checker --public --description "…" --source . --remote origin`（**不带 `--push`**） | ⬜ |
| 3 | 切换 SSH 远端并首推 | `git remote set-url origin git@github.com:yuluo554/ai-content-labeling-checker.git` → push（SSH 不受 OAuth scope 限制） | ⬜ |
| 4 | 打 tag | `git tag -a v0.1.0 -m "M6 发布"` | ⬜ |
| 5 | 打 zip 挂 Release（附件名 ASCII） | `dist/labelcheck-gui` → `labelcheck-gui-v0.1.0-win64.zip`；`dist/labelcheck` → `labelcheck-cli-v0.1.0-win64.zip`；另附演示素材 | ⬜ |
| 6 | 创建 Release | `gh release create v0.1.0 <zip…> --title "labelcheck v0.1.0" --notes-file plan/RELEASE-NOTES-v0.1.0.md` | ⬜ |
| 7 | 发布后复核 | 全新 clone → 历史三扫 + 全量测试；`gh release download` 真下载 → 核对 sha256 → 解压中立目录跑冻结态自检 | ⬜ |

**发布形态（P3 已定夺）**：只发布 **onedir 双 exe 的 zip**（免安装、解压即用），**不做安装器**。

---

## 三、待用户授权的阻塞点

1. **提交元数据邮箱改写**（§1.3）：需用户确认后执行 `filter-branch` 全历史重写。
2. **GitHub 建仓与推送**（§二）：对外发布动作，需用户确认后执行。

> 阻塞点未解除前，本文件对应条目**保持 ⬜**；解除后按实际时序回填（含任何"先做后补记"的瑕疵）。

---

## 四、发布执行实录（2026-10-13，用户授权后执行）

> **授权**：用户明确指示"按照纪律通过 github 发布"——本节记录实际执行时序与**首跑 CI 抓出的真实缺陷**。

### 4.1 执行时序（如实留痕）

| 序 | 动作 | 结果 |
|---|---|---|
| 1 | 仓外备份 `git bundle create … --all` | ✅ `_backups/labelcheck-pre-m6.bundle`（改写前留底，出仓） |
| 2 | `git config user.email/name` → noreply | ✅ `282769740+yuluo554@users.noreply.github.com` / `yuluo554` |
| 3 | 把仓内真实邮箱字面值改为保留域/描述性指代（工具夹具 + 测试夹具 + plan 文档） | ✅ 工作树与历史均 0 命中（**从未提交**，故无需 tree-filter） |
| 4 | 提交 M1–M6 累积工作 | ✅ `6b4667e`（110 文件；无 dist/build/_private） |
| 5 | `filter-branch --env-filter` 全历史改写邮箱 | ✅ 5 条旧提交改写；输出重定向到文件（**未接管道**，避免 SIGPIPE 坏 ref） |
| 6 | `rm -rf .git/refs/original` + `reflog expire --expire=now --all` + `gc --prune=now --aggressive` | ✅ 悬空对象清空 |
| 7 | **验证**：全历史 blob 扫描 + 提交信息扫描 + `log -p` 计数 + `git fsck` | ✅ 固定字面值 `<old-email-local-part>`：blob 0 / 消息 0 / patch 0；fsck 无错 |
| 8 | `gh repo create`（**不带 `--push`**）+ 切 SSH 远端 | ✅ 仓库建出；SSH 认证通过 |
| 9 | `git push -u origin main`（输出重定向，查真实退出码） | ✅ 远端 sha == 本地 sha `91d87f4`；CI 触发（workflow active） |

### 4.2 首跑 CI 抓出的真实缺陷（**本项目此前无远端 → 全项目首次 CI**）

> 这正是"推迟建仓 = 把 CI 首跑风险压进发布窗口"的反模式实录；本机 Windows 开发环境掩盖了全部三处。

| # | 失败面签名 | 缺陷 | 修复 |
|---|---|---|---|
| 1 | windows 全挂（`UnicodeEncodeError: 'charmap'`，cp1252 管道） | `tools/audit_desensitize.py` 打印中文到非 UTF-8 stdout——本机 `py -X utf8` 掩盖 | 工具内加 `_ensure_utf8_stdio()`（与 CLI 入口同口径，仅在非 UTF-8 家族时 reconfigure） |
| 2 | ubuntu `test` 挂（`ModuleNotFoundError: PySide6`） | `cmd_gui` 只把 `from ..gui import main_window` 包在 try 内——该导入**不**拖 Qt，真正的 `ImportError` 在 `build_app()` 里才抛，于是缺 extra 时抛裸异常而非 exit 3 | 把**整条用到 Qt 的路径**包进 try（build_app/main 均在 try 内） |
| 3 | `packaging-guard` 全挂（`No module named pytest`） | 该 job 装 core-only（`-e .`）却跑 pytest——dev extra 才有 pytest | CI 改为 `-e ".[dev]"`（packaging 模块零 PyInstaller 依赖的断言不变） |

**修正提交**：`git commit --amend`（显式带 `GIT_COMMITTER_EMAIL=<noreply>`，防 amend 回落旧邮箱）→ `push --force-with-lease`。

### 4.3 待回填（发布动作完成后）

- ⬜ tag `v0.1.0` + Release（挂 ASCII 命名 zip）+ 附件 sha256 留档
- ⬜ 发布后复核：全新 clone 历史三扫 + 全量测试；`gh release download` 真下载 → 核对 sha256 → 解压中立目录跑冻结态自检
- ⬜ CI 轮数与 push 数对账