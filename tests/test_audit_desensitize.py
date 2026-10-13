# -*- coding: utf-8 -*-
"""脱敏四步审计测试（M6 发布门）。

`tools/audit_desensitize.py` 不是包内模块，故用 importlib 从路径加载。覆盖：

1. **探测器阳性/阴性对照**（``selftest()``）：hex 边界环视必须既命中真手机号/身份证，
   又不误伤"含长数字串的假 sha256"——否则审计本身是空验。
2. **白名单/行内放行语义**：白名单路径与 ``audit-allow`` 标记的命中不进阻断项。
3. **真实仓库内容审计**：仓库文本内容**零阻断项**（唯一待办是需授权的提交邮箱改写）。
4. **提交邮箱读取**：能从 git 历史里读出作者/提交者邮箱并分类 noreply。
5. **资产与版权复核**：`.gitignore`/`.gitattributes`/fixtures 白名单/国标不转载全文。
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def _load_audit():
    """从 ``tools/audit_desensitize.py`` 路径加载模块（非包内模块）。"""
    path = TOOLS / "audit_desensitize.py"
    spec = importlib.util.spec_from_file_location("audit_desensitize_under_test", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit():
    return _load_audit()


# ------------------------------------------------------------------ 自检对照
def test_selftest_passes(audit):
    """阳性/阴性对照全过：规则真能命中、又不误伤已知假阳性。"""
    result = audit.selftest()
    assert result["ok"], "探测器自检未通过：\n" + "\n".join(result["failures"])
    assert result["positive_count"] >= 8
    assert result["negative_count"] >= 5


def test_phone_and_idcard_have_hex_boundary_lookaround(audit):
    """**核心断言**：phone/idcard 必须带 hex 边界环视——否则假 sha256 会误报。

    直接构造"含 18 位数字串的 64 位 hex 串"：朴素正则命中，带环视的规则不命中。
    """
    import re

    fake = "9f2a" + "138001380001234567" + "0" * 42  # audit-allow：脱敏探测夹具
    assert re.search(r"\d{17}[\dXx]", fake), "前提失效：构造串未含 17 位数字串"
    assert re.search(r"1[3-9]\d{9}", fake), "前提失效：构造串未含手机号形态"

    hits = {h["rule"] for h in audit.scan_text("<t>", fake)}
    assert "idcard18" not in hits, "idcard18 缺 hex 边界环视 → 假 sha256 误报"
    assert "phone" not in hits, "phone 缺 hex 边界环视 → 假 sha256 误报"


def test_selftest_detects_a_real_positive(audit):
    """阳性对照本身有效：真手机号/身份证必须被命中。"""
    hits = {h["rule"] for h in audit.scan_text("<t>", "手机 13800138000 身份证 11010119900307123X")}  # audit-allow：夹具
    assert "phone" in hits and "idcard18" in hits


# ------------------------------------------------------------------ 白名单/放行语义
def test_whitelisted_path_does_not_block(audit):
    """白名单路径的命中不进阻断项，但仍在白名单列表可见。"""
    findings, whitelisted, _count = audit.scan_repo_content(ROOT)
    paths = {w["path"] for w in whitelisted}
    assert "data/parse/fixtures.json" in paths or "data/knowledge/raw" in " ".join(paths)
    # 白名单放过的都不在阻断项里
    blocked = {f["path"] for f in findings}
    for entry in whitelisted:
        assert entry["path"] not in blocked


def test_allow_marker_routes_hits_to_whitelist(audit):
    """带 ``audit-allow`` 标记的行：命中转白名单，不算阻断。"""
    text = "手机号 13800138000  # audit-allow 夹具\n"
    hits = audit.scan_text("<t>", text)
    assert any(h["rule"] == "phone" for h in hits)
    line = hits[0]["source_line"]
    assert audit.ALLOW_MARKER in line


# ------------------------------------------------------------------ 真实仓库审计
def test_repo_content_audit_has_no_blocking_findings(audit):
    """仓库文本内容**零阻断项**（发布门的内容侧）。

    允许的唯一遗留是**提交邮箱**——那需要用户授权做历史重写，属单独一项。
    """
    report = audit.audit_repo(ROOT)
    assert report["blocking_count"] == 0, (
        "仓库内容存在阻断级敏感命中：\n" +
        "\n".join("{0}:{1} [{2}] {3}".format(f["path"], f["line"], f["rule"], f["match"])
                  for f in report["findings"]))
    assert report["checks"]["release_assets"]["ok"]
    assert report["checks"]["copyright_stance"]["ok"]


def test_repo_audit_scans_a_meaningful_number_of_files(audit):
    """扫描面不能是空的（防止遍历逻辑悄悄失效成"空验"）。"""
    report = audit.audit_repo(ROOT)
    assert report["scanned_files"] > 30


def test_no_personal_path_or_email_in_committed_content(audit):
    """提交内容里不得有真实用户目录路径（本机实测过的手改项）。"""
    report = audit.audit_repo(ROOT)
    for finding in report["findings"]:
        assert finding["rule"] != "personal_path", (
            "{0}:{1} 含真实用户路径：{2}".format(
                finding["path"], finding["line"], finding["match"]))


# ------------------------------------------------------------------ 提交邮箱
def test_commit_email_check_reads_history(audit):
    """能从 git 历史读出作者/提交者邮箱；分类结果自洽。"""
    result = audit.check_commit_emails(ROOT)
    if result.get("skipped"):
        pytest.skip("非 git 仓库或无提交")
    assert result["commit_count"] >= 1
    assert isinstance(result["real_emails"], list)
    # 真实邮箱与 noreply 邮箱不得重叠
    assert not (set(result["real_emails"]) & set(result["noreply_emails"]))
    # 若存在真实邮箱，必须给出"需授权 + 处置方式"
    if result["real_emails"]:
        assert result["requires_authorization"] is True
        assert "授权" in result["action"]


def test_noreply_classifier(audit):
    """noreply 判定：GitHub noreply 形态通过，真实邮箱不通过。"""
    # 以下三行是脱敏探测夹具（noreply 形态 + 真实邮箱形态），带 audit-allow 标记
    assert audit._NOREPLY_RE.match("12345+yuluo554@users.noreply.github.com")  # audit-allow 夹具
    assert audit._NOREPLY_RE.match("yuluo554@users.noreply.github.com")  # audit-allow 夹具
    assert not audit._NOREPLY_RE.match("someone@example.com")  # audit-allow 夹具（保留域）


# ------------------------------------------------------------------ CLI 端到端
def _run_audit(*args):
    env = dict(__import__("os").environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(TOOLS / "audit_desensitize.py")] + list(args),
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", env=env,
    )


def test_cli_selftest_exit_zero():
    result = _run_audit("--selftest")
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_json_is_parseable():
    result = _run_audit("--json")
    payload = json.loads(result.stdout)
    assert "blocking_count" in payload and "checks" in payload
    assert payload["blocking_count"] == 0


def test_cli_non_strict_exit_zero_when_only_email_pending():
    """非 strict：内容/资产/版权全过 → 退出码 0（邮箱项不阻断，只告警）。"""
    result = _run_audit()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "发布就绪" in result.stdout


# ------------------------------------------------------------------ 产物本体扫描
def test_artifact_scan_flags_repo_name(tmp_path, audit):
    """产物里出现仓库名 → 判未通过（构建机路径泄漏的签名之一）。"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "blob.bin").write_bytes(b"prefix 10-13-ai-content-labeling-checker suffix")
    result = audit.scan_artifacts(dist)
    assert not result["ok"]
    assert any(f["sig"] == "work_root" for f in result["findings"])


def test_artifact_scan_ignores_vendor_user_paths(tmp_path, audit):
    """**阴性对照**：上游二进制的厂商用户路径串不得误报。

    该厂商串形如"某盘符 + 用户目录 + 用户名 qt"（audit-allow：夹具按描述性指代构造，
    避免在本文件里留下可被脱敏扫描命中的路径字面量）；裸"用户目录"模式会成片误报，
    故审计器只匹配"我们的组合签名"。
    """
    dist = tmp_path / "dist"
    dist.mkdir()
    vendor = b"\x00C:" + b"\\Us" + b"ers\\qt\\build\\qtbase\x00"  # audit-allow：厂商串夹具
    (dist / "Qt6Core.dll").write_bytes(vendor)
    result = audit.scan_artifacts(dist)
    assert result["ok"], "厂商串被误报：{0}".format(result["findings"])


def test_artifact_scan_flags_forbidden_toplevel(tmp_path, audit):
    """dist 顶层混入 plan/tests/_private → 判未通过（禁区成分只查顶层）。"""
    dist = tmp_path / "dist"
    (dist / "labelcheck").mkdir(parents=True)
    (dist / "labelcheck" / "plan").mkdir()
    result = audit.scan_artifacts(dist)
    assert not result["ok"]
    assert any(f["sig"] == "forbidden_toplevel" for f in result["findings"])


def test_artifact_scan_skips_when_dist_absent(tmp_path, audit):
    """dist 不存在时跳过该步（未构建 → 不算失败）。"""
    result = audit.scan_artifacts(tmp_path / "no-such-dist")
    assert result["ok"] and result.get("skipped") is True


def test_repo_artifact_scan_passes_on_real_dist(audit):
    """仓库真实 dist（若已构建）产物本体扫描必须通过。"""
    dist = ROOT / "dist"
    if not dist.is_dir():
        pytest.skip("dist 未构建")
    result = audit.scan_artifacts(dist)
    assert result["ok"], "产物存在构建机路径/私有目录泄漏：\n" + "\n".join(
        "{0} [{1}] {2}".format(f["path"], f["sig"], f["match"]) for f in result["findings"])