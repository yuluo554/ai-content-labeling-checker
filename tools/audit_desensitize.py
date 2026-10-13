# -*- coding: utf-8 -*-
"""脱敏四步审计（M6，发布门）：发布 GitHub 前把"仓库里不该带出去的东西"扫干净。

用法：

    py -X utf8 tools/audit_desensitize.py                # 全量审计（内容 + 提交元数据 + 资产口径）
    py -X utf8 tools/audit_desensitize.py --json         # 机器可读（CI / 二次加工）
    py -X utf8 tools/audit_desensitize.py --strict       # 把"提交邮箱待改写"也算作不通过
    py -X utf8 tools/audit_desensitize.py --selftest     # 探测器阳性/阴性对照（自证非空验）
    py -X utf8 tools/audit_desensitize.py --emails       # 只看提交元数据邮箱

退出码：``0`` 通过（无阻断项） / ``1`` 有阻断项 / ``2`` 用法错误。

**四步**（对应 plan/HANDOFF-M6.md §三.1）+ **第五步产物本体扫描**：

1. **提交元数据邮箱**：``git log --format="%ae|%ce"`` 若含真实个人邮箱 → 发布前须用
   ``git filter-branch --env-filter`` / ``git filter-repo`` 全历史改写为 GitHub noreply。
   **历史重写属对外结构性动作，须用户明确授权**，故本项默认记为 ``advisory``（不阻断退出码，
   但 ``--strict`` 下阻断），并在输出里显式标注 ``requires_authorization``。
2. **已知假阳性（hex 边界环视）**：示例标识卡里的假 sha256（64 连续 hex）会命中"18 位身份证"/
   手机号正则——故 phone/idcard 模式一律加 hex 边界环视 ``(?<![0-9a-fA-F])…(?![0-9a-fA-F])``，
   并把该形态写进 ``--selftest`` 的**阴性对照**（否则探测器可能是个空验）。
3. **``data/parse/fixtures.json`` 白名单**：内含 base64 构造容器（非真实媒体），须列入
   已知假阳性白名单，并确认 ``.gitattributes`` 当文本处理（无 CR）。
4. **``data/knowledge/raw/`` 版权口径**：办法全文为行政公文（可留档）；国标**不转载全文**，
   只留书目元数据 + 条号要点对照。
5. **产物本体扫描**（``dist/**``，``--dist`` 指定）：内容级扫描证明"仓库树干净"，证明不了
   "冻结产物干净"——字节读法找**构建机路径签名 / 仓库名 / 私有目录混入**（禁区成分只查 dist
   顶层，避开依赖包自带的同名子目录）；**按组合路径签名匹配，不匹配裸用户名**（Qt DLL 等
   上游二进制内嵌厂商串会成片误报）。

另有 M0–M5 遗留的复核项：``data/**/_private/`` 已在 ``.gitignore``；``dist/``/``build/``
不入仓而 ``tools/*.spec`` 例外放行；源码/文档不得带真实用户路径与主机名。
"""

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _ensure_utf8_stdio():
    """把 stdout/stderr 切到 UTF-8（仅当当前编码不是 UTF-8 家族时）。

    本工具会打印中文；开发机 ``py -X utf8`` 会**掩盖**缺口，CI 管道是 cp1252 时
    就地崩 ``UnicodeEncodeError``（实测首跑抓到）。中文控制台（cp936）保持不动——
    它本就能显示中文；只改"会在非 ASCII 上崩"的编码。
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding in ("utf8", "utf8mb4", "cp65001"):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

#: GitHub noreply 提交邮箱（改写后的目标形态）
_NOREPLY_RE = re.compile(r"^(?:\d+\+)?[^@\s]+@users\.noreply\.github\.com$", re.IGNORECASE)

#: 扫描跳过的目录（产物/依赖/缓存；``_private`` 本就由 .gitignore 排除，此处再兜一层）
_SKIP_DIR_PARTS = (".git", "__pycache__", ".pytest_cache", "dist", "build", ".venv", "venv",
                   "node_modules", "_private", ".mypy_cache", ".ruff_cache")

#: 文本后缀白名单（只扫这些；其余（图片/二进制）不参与正则扫描）
_TEXT_SUFFIXES = (
    ".py", ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".cfg", ".ini",
    ".csv", ".gitignore", ".gitattributes", ".spec", ".lst", ".rst", ".html",
)

#: 无后缀也当文本扫的文件名
_TEXT_NAMES = ("LICENSE", ".gitignore", ".gitattributes", "Makefile")


#: 行内放行标记：命中所在行若含此标记，则该命中转为"白名单放过"（仍在输出里可见，
#: 只是不计入阻断）——供本脚本自检夹具这类**刻意构造的样本**使用。
ALLOW_MARKER = "audit-allow"


class _Rule(object):
    """一条探测规则：``name`` 供白名单引用，``severity`` ∈ {block, advisory}。"""

    def __init__(self, name, pattern, description, severity="block"):
        self.name = name
        self.pattern = re.compile(pattern)
        self.description = description
        self.severity = severity

    def __repr__(self):
        return "_Rule({0!r})".format(self.name)


#: 探测规则集。**phone/idcard 必须带 hex 边界环视**——否则示例卡里的假 sha256 会误报
#: （M0–M5 反复记录的已知假阳性；见 --selftest 阴性对照）。
#: ``long_hex`` 为 **advisory**：sha256 内容指纹是本项目的**文档化功能**（证据链），
#: 长 hex 遍地都是——只报不阻断，交人工确认"是不是合法指纹"。
RULES = (
    _Rule("email", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
          "邮箱地址"),
    _Rule("personal_path",
          r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]"
          r"[A-Za-z0-9._\-]+|/(?:home|Users)/[A-Za-z0-9._\-]+)",
          "真实用户目录路径（Windows/Unix）"),
    _Rule("phone", r"(?<![0-9a-fA-F])1[3-9]\d{9}(?![0-9a-fA-F])",
          "中国大陆手机号（hex 边界环视）"),
    _Rule("idcard18", r"(?<![0-9a-fA-F])\d{17}[\dXx](?![0-9a-fA-F])",
          "18 位身份证号（hex 边界环视）"),
    _Rule("private_key", r"BEGIN [A-Z ]*PRIVATE KEY", "私钥块"),
    _Rule("api_token", r"\b(?:ghp|gho|ghs|ghr|github_pat|sk-[A-Za-z0-9])[A-Za-z0-9_]{10,}",
          "疑似访问令牌"),
    _Rule("unc_host", r"\\\\[A-Za-z0-9._\-]+\\", "UNC 主机共享路径"),
    _Rule("private_ip",
          r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
          r"|192\.168\.\d{1,3}\.\d{1,3}"
          r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b",
          "内网 IP（RFC1918）"),
    _Rule("long_hex", r"(?<![0-9a-fA-F])[0-9a-fA-F]{40,}(?![0-9a-fA-F])",
          "长 hex 串（sha1/sha256 指纹等）", severity="advisory"),
)

#: 已知假阳性白名单：``(相对路径 glob, 规则名集合, 理由)``。
#: 命中白名单的探测**不计入阻断项**，但仍列入输出（可审计"为什么放过"）。
#: 规则名集合为空表示"该路径下所有规则命中都放过"。
WHITELIST = (
    # M6 明列：base64 构造容器（非真实媒体），长串会误报——列白名单并当文本处理
    ("data/parse/fixtures.json", (), "解析算例：base64 构造容器（非真实媒体，M6 白名单）"),
    ("data/knowledge/raw/**", (), "官方依据快照（行政公文 + 核对记录），无个人敏感信息"),
)


# ------------------------------------------------------------------ 文件遍历
def _is_text_path(path):
    if path.name in _TEXT_NAMES:
        return True
    return path.suffix.lower() in _TEXT_SUFFIXES


def _skip_dir(part):
    return part in _SKIP_DIR_PARTS


def iter_scan_files(root):
    """产出待扫描的**文本**文件（跳过产物/依赖/缓存/私有件目录）。

    优先用 ``git ls-files``（含未跟踪但未忽略者）——这样"新写的 M6 文件"也会被扫到；
    无 git 或非仓库时退化为 ``rglob``。
    """
    root = Path(root)
    rels = _git_list_files(root)
    if rels is not None:
        paths = [root / rel for rel in rels]
    else:
        paths = sorted(p for p in root.rglob("*") if p.is_file())

    for path in paths:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if any(_skip_dir(part) for part in Path(rel).parts[:-1]):
            continue
        if not _is_text_path(path):
            continue
        yield rel, path


def _git_list_files(root):
    """``git ls-files --cached --others --exclude-standard``；非仓库/无 git 返回 None。"""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8",
        )
    except (OSError, ValueError):
        return None
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


def _read_text(path):
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    return data.decode("utf-8", errors="replace")


# ------------------------------------------------------------------ 内容扫描
#: git 传输地址（`git@host:...` / `ssh://git@host/...`）是**服务地址**，不是个人邮箱——
#: 发布固有公开元数据，不算泄露（系列实录：只豁免 HTTPS 形态会在 SSH 留档行误报硬门）。
_GIT_SERVICE_EMAIL_RE = re.compile(r"^(?:git|ssh|hg)@[A-Za-z0-9.\-]+$")


def scan_text(rel, text):
    """扫一段文本，返回命中列表 ``[{rule, line, match, snippet, source_line}]``。"""
    hits = []
    lines = text.splitlines()
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            value = match.group(0)
            if rule.name == "email" and _GIT_SERVICE_EMAIL_RE.match(value):
                continue  # git 传输地址，非个人邮箱
            if rule.name == "email" and _NOREPLY_RE.match(value):
                continue  # GitHub noreply = 已脱敏的目标形态（发布固有公开值）
            line = text.count("\n", 0, match.start()) + 1
            hits.append({
                "rule": rule.name,
                "line": line,
                "match": value[:120],
                "snippet": _snippet(text, match.start()),
                "source_line": lines[line - 1] if 0 < line <= len(lines) else "",
            })
    return hits


def _snippet(text, index, width=48):
    start = max(0, index - width)
    end = min(len(text), index + width)
    return text[start:end].replace("\n", " ").strip()


def _whitelist_reason(rel, rule_name):
    for pattern, rules, reason in WHITELIST:
        if not rules or rule_name in rules:
            if fnmatch.fnmatch(rel, pattern):
                return reason
    return None


def scan_repo_content(root):
    """扫描仓库文本内容；返回 ``(findings, whitelisted, scanned_count)``。

    只有**阻断级**且未命中白名单/行内放行标记的命中才进 ``findings``；
    advisory（如 ``long_hex``）、白名单路径、带 ``audit-allow`` 标记的行都进 ``whitelisted``
    （仍可见，只是不计入阻断）。
    """
    findings = []
    whitelisted = []
    count = 0
    for rel, path in iter_scan_files(root):
        text = _read_text(path)
        if text is None:
            continue
        count += 1
        for hit in scan_text(rel, text):
            entry = dict(hit, path=rel)
            entry.pop("source_line", None)
            reason = _whitelist_reason(rel, hit["rule"])
            if reason:
                entry["whitelist_reason"] = reason
                whitelisted.append(entry)
                continue
            if _severity_of(hit["rule"]) != "block":
                entry["whitelist_reason"] = "advisory（长 hex/指纹类，只报不阻断）"
                whitelisted.append(entry)
                continue
            if ALLOW_MARKER in hit["source_line"]:
                entry["whitelist_reason"] = "行内 {0} 标记（刻意构造的样本）".format(ALLOW_MARKER)
                whitelisted.append(entry)
                continue
            findings.append(entry)
    return findings, whitelisted, count


# ------------------------------------------------------------------ 第一步：提交邮箱
def check_commit_emails(root):
    """读全历史作者/提交者邮箱，列出非 noreply 者（发布前须改写）。"""
    result = subprocess.run(
        ["git", "log", "--format=%ae|%ce"], cwd=str(root),
        capture_output=True, text=True, encoding="utf-8",
    ) if _has_git(root) else None
    if result is None or result.returncode != 0:
        return {"ok": True, "skipped": True, "reason": "非 git 仓库或无提交",
                "real_emails": [], "noreply_emails": [], "commit_count": 0}

    real, noreply, count = {}, {}, 0
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        count += 1
        for email in line.split("|"):
            email = email.strip()
            if not email:
                continue
            if _NOREPLY_RE.match(email):
                noreply[email] = noreply.get(email, 0) + 1
            else:
                real[email] = real.get(email, 0) + 1

    return {
        "ok": not real,
        "skipped": False,
        "requires_authorization": bool(real),
        "action": ("用 git filter-branch --env-filter（或 git-filter-repo）把全历史作者/提交者"
                   "邮箱改写为 GitHub noreply，并同步 git config user.email"
                   "（历史重写属对外结构性动作，须用户明确授权）"),
        "real_emails": sorted(real),
        "noreply_emails": sorted(noreply),
        "commit_count": count,
    }


def _has_git(root):
    try:
        result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                                cwd=str(root), capture_output=True, text=True)
    except (OSError, ValueError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


# ------------------------------------------------------------------ 第五步：构建产物本体扫描
# 内容级扫描证明"仓库树干净"，证明不了"冻结产物干净"——exe/onedir 内嵌的源码路径、构建机
# 路径要单独扫。**按组合路径签名匹配，不匹配裸词**：Qt DLL 等上游二进制内嵌 `\Users\qt`、
# `ASUSTek COMPUTER INC` 一类厂商串，裸 `Users\` / 用户名片段会成片误报（系列实录）。
# 真实泄露面 = "我们的工作根/仓库名/私有目录"出现在产物树**顶层**。
_ARTIFACT_SIGS = (
    ("repo_name", re.compile(rb"ai-content-labeling-checker")),
    ("work_root", re.compile(rb"10-13-ai-content-labeling-checker")),
    ("programdata_path", re.compile(rb"[A-Za-z]:[\\/]ProgramData[\\/]")),
    ("home_user_path", re.compile(rb"[A-Za-z]:[\\/]Users[\\/](?!qt\b)[A-Za-z0-9._\-]{2,}")),
)

#: 产物顶层不得出现的"禁区成分"（我们的 plan/tests/私有件混入发行包）
_ARTIFACT_FORBIDDEN_TOPLEVEL = ("plan", "tests", "tools", "_private", ".git", ".github")


def scan_artifacts(dist_dir):
    """扫构建产物（dist/**）：字节读法找构建机路径/仓库名/私有目录混入。

    只匹配**组合路径签名**（不匹配裸用户名，避开 Qt 等上游二进制的厂商串）；
    且"禁区成分"只查 dist **顶层**（依赖包自带的 `tests/` 子目录不算泄露）。
    """
    dist_dir = Path(dist_dir)
    if not dist_dir.is_dir():
        return {"ok": True, "skipped": True, "reason": "dist 目录不存在（未构建）",
                "findings": [], "scanned_files": 0, "toplevel_entries": []}

    findings = []
    scanned = 0
    for path in sorted(dist_dir.rglob("*")):
        if not path.is_file():
            continue
        scanned += 1
        try:
            data = path.read_bytes()
        except OSError:
            continue
        rel = path.relative_to(dist_dir).as_posix()
        for name, pattern in _ARTIFACT_SIGS:
            for match in pattern.finditer(data):
                findings.append({"path": rel, "sig": name,
                                 "match": match.group(0)[:80].decode("latin-1")})
                break  # 每文件每签名只记一次，避免刷屏

    # 禁区成分只查 dist 顶层
    toplevel = sorted(p.name for p in dist_dir.iterdir()) if dist_dir.is_dir() else []
    # dist 下可能有多个 exe 子目录（labelcheck/、labelcheck-gui/），各查其顶层
    toplevel_entries = []
    for sub in [dist_dir] + [p for p in dist_dir.iterdir() if p.is_dir()]:
        names = sorted(p.name for p in sub.iterdir())
        toplevel_entries.append({"dir": sub.name if sub != dist_dir else ".",
                                 "names": names})
        for name in names:
            if name in _ARTIFACT_FORBIDDEN_TOPLEVEL:
                findings.append({"path": sub.name + "/" + name, "sig": "forbidden_toplevel",
                                 "match": name})

    return {"ok": not findings, "skipped": False, "findings": findings,
            "scanned_files": scanned, "toplevel_entries": toplevel_entries}


# ------------------------------------------------------------------ 第三步：白名单与属性
def check_release_assets(root):
    """复核 fixtures 白名单 / .gitattributes / .gitignore（M0–M5 遗留项）。"""
    root = Path(root)
    problems = []

    attrs_path = root / ".gitattributes"
    attrs = attrs_path.read_text(encoding="utf-8") if attrs_path.is_file() else ""
    if "text=auto" not in attrs or "eol=lf" not in attrs:
        problems.append(".gitattributes 缺少 text=auto / eol=lf（跨平台字节一致前提）")

    fixtures = root / "data" / "parse" / "fixtures.json"
    fixtures_whitelisted = False
    if not fixtures.is_file():
        problems.append("data/parse/fixtures.json 缺失（解析通路算例）")
    else:
        if b"\r" in fixtures.read_bytes():
            problems.append("data/parse/fixtures.json 含 CR（应作为 LF 文本资产）")
        fixtures_whitelisted = any(
            fnmatch.fnmatch("data/parse/fixtures.json", pattern)
            for pattern, _rules, _reason in WHITELIST
        )
        if not fixtures_whitelisted:
            problems.append("data/parse/fixtures.json 未列入脱敏白名单（base64 构造容器会误报）")

    ignore_path = root / ".gitignore"
    ignore = ignore_path.read_text(encoding="utf-8") if ignore_path.is_file() else ""
    if "data/**/_private/" not in ignore:
        problems.append(".gitignore 缺少 data/**/_private/（本地私有件不入仓）")
    if "!tools/*.spec" not in ignore:
        problems.append(".gitignore 缺少 !tools/*.spec（构建脚本须入仓的例外放行）")

    private_tracked = [p for p in (_git_list_files(root) or []) if "_private" in Path(p).parts]
    if private_tracked:
        problems.append("存在被跟踪的 _private 文件：{0}".format(", ".join(private_tracked[:5])))

    dist_tracked = [p for p in (_git_list_files(root) or [])
                    if Path(p).parts and Path(p).parts[0] in ("dist", "build")]
    if dist_tracked:
        problems.append("存在被跟踪的构建产物：{0}".format(", ".join(dist_tracked[:5])))

    return {
        "ok": not problems,
        "problems": problems,
        "fixtures_whitelisted": fixtures_whitelisted,
        "private_dir_ignored": "data/**/_private/" in ignore,
        "spec_exception_present": "!tools/*.spec" in ignore,
    }


# ------------------------------------------------------------------ 第四步：版权口径
def check_copyright_stance(root):
    """复核 data/knowledge/raw/ 的版权口径：国标不转载全文，行政公文可留档。"""
    root = Path(root)
    problems = []
    gb_dir = root / "data" / "knowledge" / "raw" / "gb45438-2025"
    gb_files = sorted(p.name for p in gb_dir.glob("*")) if gb_dir.is_dir() else []
    if not gb_dir.is_dir():
        problems.append("data/knowledge/raw/gb45438-2025/ 缺失")
    else:
        fulltext = [name for name in gb_files if not name.endswith("-verification.md")]
        if fulltext:
            problems.append("国标目录含疑似全文文件（只应留核对记录）：{0}".format(
                ", ".join(fulltext)))
        verification = gb_dir / "2025-09-01-verification.md"
        if verification.is_file():
            text = verification.read_text(encoding="utf-8")
            if "不转载" not in text:
                problems.append("国标核对记录未声明'不转载标准全文'")
        else:
            problems.append("缺少国标核对记录 2025-09-01-verification.md")

    measures_dir = root / "data" / "knowledge" / "raw" / "labeling-measures"
    measures = list(measures_dir.glob("*fulltext*")) if measures_dir.is_dir() else []
    if not measures:
        problems.append("data/knowledge/raw/labeling-measures/ 缺少办法全文快照（行政公文可留档）")

    return {"ok": not problems, "problems": problems, "gb_files": gb_files,
            "measures_fulltext": [p.name for p in measures]}


# ------------------------------------------------------------------ 汇总
def audit_repo(root, dist_dir=None):
    findings, whitelisted, scanned = scan_repo_content(root)
    emails = check_commit_emails(root)
    assets = check_release_assets(root)
    copyright_ = check_copyright_stance(root)
    artifacts = scan_artifacts(dist_dir if dist_dir is not None else Path(root) / "dist")

    blocking = [f for f in findings if _severity_of(f["rule"]) == "block"]
    ok = not blocking and assets["ok"] and copyright_["ok"] and artifacts["ok"]
    return {
        "root": str(Path(root).resolve()),
        "ok": ok,
        "publish_ready": ok and (emails["ok"] or emails.get("skipped", False)),
        "scanned_files": scanned,
        "findings": findings,
        "whitelisted": whitelisted,
        "blocking_count": len(blocking),
        "checks": {
            "commit_emails": emails,
            "release_assets": assets,
            "copyright_stance": copyright_,
            "artifacts": artifacts,
        },
    }


def _severity_of(rule_name):
    for rule in RULES:
        if rule.name == rule_name:
            return rule.severity
    return "block"


# ------------------------------------------------------------------ 自检（阳性/阴性对照）
# 说明：以下夹具是**刻意构造的样本**，必然命中探测器——故每行带 ``audit-allow`` 行内标记，
# 使自己扫描本文件时转为"白名单放过"（而不是把审计工具自己报成泄露）。
_POSITIVE = (
    ("email", "请联系 someone@example.com 处理"),        # audit-allow 夹具（保留域）
    ("phone", "手机号 13800138000"),                    # audit-allow 夹具
    ("idcard18", "身份证 11010119900307123X"),          # audit-allow 夹具
    ("personal_path", r"路径 C:\Users\zhangsan\AppData\Local"),  # audit-allow 夹具
    ("personal_path", "路径 /home/zhangsan/work"),      # audit-allow 夹具
    ("private_key", "-----BEGIN RSA PRIVATE KEY-----"),  # audit-allow 夹具
    ("api_token", "ghp_" + "A" * 36),                   # audit-allow 夹具
    ("unc_host", r"共享 \\FILESERVER\share"),           # audit-allow 夹具
    ("private_ip", "内网 192.168.1.10"),                # audit-allow 夹具
    ("long_hex", "a" * 64),                             # audit-allow 夹具
)

#: 已知假阳性形态（M0–M5 反复记录）：64 连续 hex 的**假 sha256**里可能嵌着长数字串
#: （示例卡/真值库的 content_sha256 就是这种构造），朴素正则会把其中的数字串当身份证/手机号。
#: 这里刻意构造一个**含 18 位数字串**的 64 位 hex 串，验证 hex 边界环视能拦住。
_FAKE_SHA_WITH_DIGITS = "9f2a" + "138001380001234567" + "0" * 42  # audit-allow：4+18+42=64 hex 夹具

#: 阴性对照：**必须不命中** phone/idcard/personal_path。
_NEGATIVE = (
    ("假 sha256（64 hex 含长数字串）不得当身份证/手机号",
     _FAKE_SHA_WITH_DIGITS, ("phone", "idcard18")),
    ("仓库真实示例件 sha256 不得当身份证/手机号",
     "31e27b3cefccd2bedc76c1e5298aacccb9af4e31003290b96579b4c60fb031b8",  # audit-allow 夹具
     ("phone", "idcard18")),
    ("全 a 的 64 hex 不得当身份证",
     "a" * 64, ("phone", "idcard18")),
    ("YAML 行（steps:/jobs:）不得当盘符路径",
     "    steps:\n      jobs:\n", ("personal_path",)),
    ("URL（https://…）不得当盘符路径",
     "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo", ("personal_path",)),
    ("版本号 6.6.3.1 不得当内网 IP",
     "PySide6 6.6.3.1", ("private_ip",)),
    ("git 传输地址不得当个人邮箱",
     "git remote set-url origin git@github.com:owner/repo.git", ("email",)),
    ("GitHub noreply（已脱敏目标形态）不得当个人邮箱",
     "282769740+yuluo554@users.noreply.github.com", ("email",)),
)


def selftest():
    """探测器阳性/阴性对照：证明规则**真能命中**、又**不误伤**已知假阳性。"""
    failures = []

    for rule_name, sample in _POSITIVE:
        hits = {h["rule"] for h in scan_text("<selftest>", sample)}
        if rule_name not in hits:
            failures.append("阳性对照未命中：{0} ← {1!r}".format(rule_name, sample))

    for label, sample, must_not in _NEGATIVE:
        hits = {h["rule"] for h in scan_text("<selftest>", sample)}
        for rule_name in must_not:
            if rule_name in hits:
                failures.append("阴性对照误报：{0}（{1} 命中 {2!r}）".format(
                    label, rule_name, sample))

    # 直接钉死"hex 边界环视"这一条：**去掉环视的朴素正则确实会误报**（前提有效），
    # 而带环视的规则不会命中——否则本对照就是空验。
    naive_idcard = re.search(r"\d{17}[\dXx]", _FAKE_SHA_WITH_DIGITS)
    naive_phone = re.search(r"1[3-9]\d{9}", _FAKE_SHA_WITH_DIGITS)
    if naive_idcard is None or naive_phone is None:
        failures.append("阴性对照前提失效：构造的假 sha256 未被朴素正则命中"
                        "（对照失去意义，须调整构造）")
    for rule_name in ("idcard18", "phone"):
        if any(h["rule"] == rule_name
               for h in scan_text("<selftest>", _FAKE_SHA_WITH_DIGITS)):
            failures.append("hex 边界环视失效：假 sha256 被 {0} 命中".format(rule_name))

    return {"ok": not failures, "failures": failures,
            "positive_count": len(_POSITIVE), "negative_count": len(_NEGATIVE)}


# ------------------------------------------------------------------ CLI
def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="脱敏四步审计（M6 发布门）")
    parser.add_argument("--root", default=str(_ROOT), help="仓库根（默认脚本所在仓库）")
    parser.add_argument("--dist", default=None, metavar="DIR",
                        help="构建产物目录（默认 <root>/dist；不存在则跳过该步）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--strict", action="store_true",
                        help="把'提交邮箱待改写'也计为不通过（发布前最终门）")
    parser.add_argument("--emails", action="store_true", help="只看提交元数据邮箱")
    parser.add_argument("--selftest", action="store_true",
                        help="只跑探测器阳性/阴性对照")
    args = parser.parse_args(argv)

    if args.selftest:
        result = selftest()
        if args.json:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            sys.stdout.write("探测器自检：{0}（阳性 {1} / 阴性 {2}）\n".format(
                "通过" if result["ok"] else "未通过",
                result["positive_count"], result["negative_count"]))
            for failure in result["failures"]:
                sys.stdout.write("  ✗ {0}\n".format(failure))
        return 0 if result["ok"] else 1

    if args.emails:
        result = check_commit_emails(args.root)
        if args.json:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            _print_emails(result)
        return 0 if result["ok"] else 1

    report = audit_repo(args.root, dist_dir=args.dist)
    if args.json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    else:
        _print_report(report)

    ok = report["ok"] and (not args.strict or report["checks"]["commit_emails"]["ok"])
    return 0 if ok else 1


def _print_emails(emails):
    if emails.get("skipped"):
        sys.stdout.write("提交邮箱：跳过（{0}）\n".format(emails["reason"]))
        return
    sys.stdout.write("提交邮箱（共 {0} 条提交）：\n".format(emails["commit_count"]))
    sys.stdout.write("  noreply : {0}\n".format(", ".join(emails["noreply_emails"]) or "（无）"))
    if emails["real_emails"]:
        sys.stdout.write("  ⚠ 真实邮箱（须授权后全历史改写）：{0}\n".format(
            ", ".join(emails["real_emails"])))
        sys.stdout.write("  处置：{0}\n".format(emails["action"]))
    else:
        sys.stdout.write("  真实邮箱：无（全部为 noreply）\n")


def _print_report(report):
    sys.stdout.write("脱敏审计：{0}（扫描 {1} 个文本文件）\n".format(
        "通过" if report["ok"] else "有阻断项", report["scanned_files"]))

    findings = report["findings"]
    sys.stdout.write("  [内容] 阻断项 {0} 个 / 白名单放过 {1} 个\n".format(
        len(findings), len(report["whitelisted"])))
    for hit in findings:
        sys.stdout.write("      ✗ {0}:{1} [{2}] {3}\n".format(
            hit["path"], hit["line"], hit["rule"], hit["match"]))
    for hit in report["whitelisted"]:
        sys.stdout.write("      · {0}:{1} [{2}] 白名单：{3}\n".format(
            hit["path"], hit["line"], hit["rule"], hit["whitelist_reason"]))

    assets = report["checks"]["release_assets"]
    sys.stdout.write("  [资产] {0}\n".format("通过" if assets["ok"] else "未通过"))
    for problem in assets["problems"]:
        sys.stdout.write("      ✗ {0}\n".format(problem))

    copyright_ = report["checks"]["copyright_stance"]
    sys.stdout.write("  [版权] {0}\n".format("通过" if copyright_["ok"] else "未通过"))
    for problem in copyright_["problems"]:
        sys.stdout.write("      ✗ {0}\n".format(problem))

    artifacts = report["checks"]["artifacts"]
    if artifacts.get("skipped"):
        sys.stdout.write("  [产物] 跳过（{0}）\n".format(artifacts["reason"]))
    else:
        sys.stdout.write("  [产物] {0}（扫描 {1} 个文件）\n".format(
            "通过" if artifacts["ok"] else "未通过", artifacts["scanned_files"]))
        for hit in artifacts["findings"]:
            sys.stdout.write("      ✗ {0} [{1}] {2}\n".format(
                hit["path"], hit["sig"], hit["match"]))

    emails = report["checks"]["commit_emails"]
    sys.stdout.write("  [邮箱] {0}\n".format(
        "通过" if emails["ok"] else "⚠ 待用户授权改写历史"))
    _print_emails(emails)

    sys.stdout.write("发布就绪：{0}\n".format("是" if report["publish_ready"] else "否"))


if __name__ == "__main__":
    sys.exit(main())