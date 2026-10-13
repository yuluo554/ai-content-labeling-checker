"""EOL 门 + 零政策字面量门 + 冻结数据完整性。

**EOL 门**（系列踩坑）：Windows 全局 ``core.autocrlf=true`` 会把全新 clone 的 LF
重写成 CRLF，让逐字节冻结的 fixtures 全挂——只有"开发机本机的全新 clone"能暴露。
故：``data/**`` 是冻结数据资产，出现 CR 即**大声失败**。

**零政策字面量门**：规则库的数值/格式约束只能来自数据文件，不得抄进代码成为
"第二份真相"。豁免口径 = 小于 100 的日历/精度常数（年龄/位数等）。
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SRC = ROOT / "src"

#: 受扫描的源码范围（引擎/基准/前端；M0 为 src 全量）
SCANNED_SUFFIXES = (".py",)


def _iter_data_files():
    for path in sorted(DATA.rglob("*")):
        if path.is_file():
            yield path


# ------------------------------------------------------------------ EOL 门
def _has_cr(path):
    return b"\r" in path.read_bytes()


def test_no_cr_in_frozen_data_files():
    """冻结数据资产（data/**）不得含 CR——跨平台字节一致的前提。"""
    offenders = []
    for path in _iter_data_files():
        if _has_cr(path):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, (
        "冻结数据资产出现 CR（行尾漂移，会打挂跨平台复现）：\n" + "\n".join(offenders) +
        "\n处置：以 newline='\\n' 重写文件（不要放宽本测试）"
    )


def test_eol_detector_positive_control(tmp_path):
    """**阳性对照**：确认 CR 探测逻辑本身有效（否则上面的门可能是空验）。"""
    crlf = tmp_path / "crlf.json"
    crlf.write_bytes(b'{\r\n  "a": 1\r\n}\r\n')
    assert _has_cr(crlf), "CR 探测失效——EOL 门会变成空验"

    lf = tmp_path / "lf.json"
    lf.write_bytes(b'{\n  "a": 1\n}\n')
    assert not _has_cr(lf)


def test_gitattributes_enforces_lf():
    """仓库必须声明 eol=lf（EOL 门的地基，缺了它上面的测试只在 CI 才拦得住）。"""
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "text=auto" in text and "eol=lf" in text


# ------------------------------------------------------------------ 数据文件结构
def test_registry_is_valid_json_and_has_required_docs():
    registry = json.loads((DATA / "rules" / "registry.json").read_text(encoding="utf-8"))
    doc_ids = [d["doc_id"] for d in registry["documents"]]
    assert "labeling-measures" in doc_ids
    assert "gb45438-2025" in doc_ids
    assert set(registry["active"]) == set(doc_ids), "每个注册文档都须声明生效版本"


def test_every_ruleset_file_exists_and_matches_registry():
    registry = json.loads((DATA / "rules" / "registry.json").read_text(encoding="utf-8"))
    for doc in registry["documents"]:
        for ver in doc["versions"]:
            path = DATA / "rules" / ver["rules_file"]
            assert path.is_file(), "注册表引用的规则文件不存在：{0}".format(ver["rules_file"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert payload["doc_id"] == doc["doc_id"]
            assert payload["version"] == ver["version"]


def test_shipped_rules_all_pending():
    """M0 纪律：随附规则条目必须全部 pending（未核对不得生效）。"""
    registry = json.loads((DATA / "rules" / "registry.json").read_text(encoding="utf-8"))
    for doc in registry["documents"]:
        for ver in doc["versions"]:
            payload = json.loads((DATA / "rules" / ver["rules_file"]).read_text(encoding="utf-8"))
            for rule in payload["rules"]:
                assert rule["status"] == "pending", (
                    "M0 不得有 verified 条目（须先挂原文核对）：{0}".format(rule["rule_id"])
                )


def test_shipped_documents_all_pending():
    registry = json.loads((DATA / "rules" / "registry.json").read_text(encoding="utf-8"))
    for doc in registry["documents"]:
        assert doc["status"] == "pending", "M0 文档状态应为 pending：{0}".format(doc["doc_id"])


def test_shipped_mapping_fields_all_pending():
    mapping = json.loads((DATA / "mapping" / "national-fields.json").read_text(encoding="utf-8"))
    for field in mapping["fields"]:
        assert field["status"] == "pending", "M0 映射字段应为 pending：{0}".format(field["national_field"])


def test_every_pending_rule_declares_article_placeholder():
    """即便 pending，也要有 clause.article 占位——避免"忘了挂依据"落库。"""
    registry = json.loads((DATA / "rules" / "registry.json").read_text(encoding="utf-8"))
    for doc in registry["documents"]:
        for ver in doc["versions"]:
            payload = json.loads((DATA / "rules" / ver["rules_file"]).read_text(encoding="utf-8"))
            for rule in payload["rules"]:
                assert rule.get("clause", {}).get("article"), (
                    "规则缺 clause.article：{0}".format(rule["rule_id"])
                )
                assert rule.get("source_url"), "规则缺 source_url：{0}".format(rule["rule_id"])


# ------------------------------------------------------------------ 零政策字面量门
#: 规则库里出现的、**不得抄进代码**的取值/格式串（M0 规则库里的占位枚举）
FORBIDDEN_POLICY_TOKENS = (
    "AI_GENERATED",
    "AI_SYNTHETIC",
    "AI_EDITED",
    "SYN-0001",
    "service.provider.name",
    "service.provider.code",
    "content.property",
)

#: 豁免：数值型日历/精度常数（<100）不在此门禁范围
def test_policy_tokens_absent_from_engine_sources():
    """规则取值不得硬编码进引擎源码（含 docstring/注释）：

    数值与枚举只能来自规则库/映射表数据文件——否则就是"抄进代码的第二份真相"。
    """
    violations = []
    for path in sorted(SRC.rglob("*.py")):
        if path.relative_to(SRC).parts[0] == "gui":
            continue
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_POLICY_TOKENS:
            if token in text:
                violations.append("{0} 含禁用 token {1!r}".format(
                    path.relative_to(ROOT).as_posix(), token))
    assert not violations, (
        "引擎源码出现规则库取值（应只从数据文件读取）：\n" + "\n".join(violations)
    )


def test_no_timestamps_written_by_engine_sources():
    """产物确定性：引擎源码不得调用 datetime.now / time.time 写产物。"""
    forbidden = ("datetime.now(", "datetime.today()", "time.time()", "utcnow(")
    violations = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                violations.append("{0} 含 {1}".format(
                    path.relative_to(ROOT).as_posix(), token))
    assert not violations, (
        "引擎源码使用系统时钟（产物将不可复现；时间须由调用方传入）：\n" + "\n".join(violations)
    )
