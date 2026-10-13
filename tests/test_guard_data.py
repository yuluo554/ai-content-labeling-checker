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


def test_shipped_rules_have_valid_status_and_verified_entries_are_traceable():
    """M1 纪律：条目 status ∈ {verified,pending}；**verified 条目必须挂条号 + 出处 + 核对日**。

    （M0 的"全部 pending"断言已随 M1 数据核对完成而更新——门控语义本身由
    ``test_rules_gate.py`` 用临时数据锁死，不依赖随附数据的 pending 比例。）
    """
    registry = json.loads((DATA / "rules" / "registry.json").read_text(encoding="utf-8"))
    verified_seen = 0
    for doc in registry["documents"]:
        for ver in doc["versions"]:
            payload = json.loads((DATA / "rules" / ver["rules_file"]).read_text(encoding="utf-8"))
            for rule in payload["rules"]:
                assert rule["status"] in ("verified", "pending"), (
                    "非法 status：{0}".format(rule["rule_id"])
                )
                if rule["status"] == "verified":
                    verified_seen += 1
                    assert rule.get("clause", {}).get("article"), (
                        "verified 条目必须挂条号：{0}".format(rule["rule_id"]))
                    assert rule.get("source_url"), (
                        "verified 条目必须挂出处：{0}".format(rule["rule_id"]))
                    assert rule.get("verified_at"), (
                        "verified 条目必须挂核对日：{0}".format(rule["rule_id"]))
    assert verified_seen > 0, "M1 后随附规则库应含已核对条目"


def test_shipped_documents_status_matches_rule_verification():
    """文档 status 与条目核对状态一致：有 verified 条目的文档不得仍是 pending。"""
    registry = json.loads((DATA / "rules" / "registry.json").read_text(encoding="utf-8"))
    for doc in registry["documents"]:
        has_verified = False
        for ver in doc["versions"]:
            payload = json.loads((DATA / "rules" / ver["rules_file"]).read_text(encoding="utf-8"))
            if any(r["status"] == "verified" for r in payload["rules"]):
                has_verified = True
        if has_verified:
            assert doc["status"] == "verified", (
                "含 verified 条目的文档却标 pending（双重门控会让条目全部失效）：{0}".format(
                    doc["doc_id"]))


def test_shipped_mapping_fields_have_traceable_source():
    """映射字段：status ∈ {verified,pending}；verified 字段必须挂条号与出处。"""
    mapping = json.loads((DATA / "mapping" / "national-fields.json").read_text(encoding="utf-8"))
    for field in mapping["fields"]:
        assert field["status"] in ("verified", "pending"), (
            "非法 status：{0}".format(field["national_field"]))
        if field["status"] == "verified":
            assert field.get("clause", {}).get("article"), (
                "verified 映射字段必须挂条号：{0}".format(field["national_field"]))
            assert field.get("source_url"), (
                "verified 映射字段必须挂出处：{0}".format(field["national_field"]))


def test_shipped_registry_declares_sha256_for_every_version():
    """M1 后每个版本的规则文件都必须登记 sha256（数据真伪门生效）。"""
    registry = json.loads((DATA / "rules" / "registry.json").read_text(encoding="utf-8"))
    for doc in registry["documents"]:
        for ver in doc["versions"]:
            sha = ver.get("sha256")
            assert isinstance(sha, str) and len(sha) == 64, (
                "版本 {0}@{1} 未登记合法 sha256：{2!r}".format(
                    doc["doc_id"], ver["version"], sha))


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


# ------------------------------------------------------------------ M2 适用性画像守门
def _all_shipped_rules():
    registry = json.loads((DATA / "rules" / "registry.json").read_text(encoding="utf-8"))
    for doc in registry["documents"]:
        for ver in doc["versions"]:
            payload = json.loads((DATA / "rules" / ver["rules_file"]).read_text(encoding="utf-8"))
            for rule in payload["rules"]:
                yield doc["doc_id"], rule


def test_propagation_implicit_rules_are_scenario_gated_and_verified():
    """传播要素（§6.1 a) 4) 5)）必须**场景门控 + verified**（M2 适用性画像）。

    M1 时因"传播场景适用性未画像"保持 pending；M2 建立画像后转 verified。
    若有人删掉 ``only_if.scenario`` 而保留 verified，规则会在非传播场景下误判缺失
    ——这正是本守门要拦住的回归。
    """
    gated = []
    for doc_id, rule in _all_shipped_rules():
        if rule["rule_id"] in ("gb45438:implicit:content_propagator.presence",
                               "gb45438:implicit:propagate_id.presence"):
            assert rule["status"] == "verified", (
                "M2 后传播要素应已按适用性画像转 verified：{0}".format(rule["rule_id"]))
            scenarios = (rule.get("only_if") or {}).get("scenario")
            assert scenarios == ["propagated"], (
                "传播要素必须门控在 propagated 场景（否则非传播场景误判）：{0}".format(
                    rule["rule_id"]))
            gated.append(rule["rule_id"])
    assert len(gated) == 2, "未找到两条传播要素规则"


def test_uniqueness_rule_exists_and_is_verified():
    """§6.1 c)「仅保留一份文件元数据隐式标识」须有生效的 unique 规则（M2 新增）。"""
    found = False
    for doc_id, rule in _all_shipped_rules():
        if rule["check_type"] == "unique":
            assert rule["status"] == "verified", "unique 规则须已核对生效"
            assert rule["scope"] == "implicit", "unique 只适用于 implicit scope"
            assert rule["clause"]["article"] == "6.1 c)", (
                "unique 规则条号应为 6.1 c)：{0}".format(rule["rule_id"]))
            found = True
    assert found, "缺少 §6.1 c) 唯一性规则"


def test_measures_unique_obligations_are_verified_and_gated():
    """办法独有义务（导出文件/传播平台提示）须 verified 且带场景门控（M2）。"""
    expected = {
        "measures:explicit:export.file.label.presence": ["exported"],
        "measures:propagation:platform.hint.presence": ["propagated"],
    }
    seen = {}
    for doc_id, rule in _all_shipped_rules():
        if rule["rule_id"] in expected:
            assert doc_id == "labeling-measures"
            assert rule["status"] == "verified", (
                "办法独有义务已在 M2 适用性画像后转 verified：{0}".format(rule["rule_id"]))
            seen[rule["rule_id"]] = (rule.get("only_if") or {}).get("scenario")
    assert seen == expected, "办法独有义务的场景门控不符：{0}".format(seen)


def test_measures_rules_sharing_gb_targets_stay_pending():
    """与国标同 target 的办法条目**必须保持 pending**（避免同目标双份 Finding）。"""
    gb_targets = set()
    for doc_id, rule in _all_shipped_rules():
        if doc_id == "gb45438-2025":
            gb_targets.add((rule["scope"], rule["target"]))

    for doc_id, rule in _all_shipped_rules():
        if doc_id != "labeling-measures":
            continue
        key = (rule["scope"], rule["target"])
        if key in gb_targets and rule["status"] != "pending":
            # 例外：unique 类不重复（国标侧为独立条件），排除
            assert rule["check_type"] != "unique", rule["rule_id"]
            raise AssertionError(
                "办法条目与国标同 target 却已 verified（会双份 Finding）：{0} → {1}".format(
                    rule["rule_id"], key))


def test_parse_profile_wrapper_is_data_driven():
    """解析画像的载荷包裹键必须在映射表数据里（解析器不得硬编码政策键名）。"""
    mapping = json.loads((DATA / "mapping" / "national-fields.json").read_text(encoding="utf-8"))
    profile = mapping.get("parse_profile") or {}
    assert profile.get("payload_wrapper"), "映射表缺 parse_profile.payload_wrapper"
    assert profile.get("source_clause"), "解析画像须挂条款出处"


def test_parse_fixtures_are_registered_and_parseable():
    """解析算例夹具须存在、结构完整（真值字段齐全），且每例有真实字节。"""
    import base64
    path = DATA / "parse" / "fixtures.json"
    assert path.is_file(), "缺少 data/parse/fixtures.json（跑 tools/gen_parse.py）"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["fixtures"], "解析算例不得为空"
    for item in payload["fixtures"]:
        for key in ("fixture_id", "container", "carrier", "bytes_b64", "expected"):
            assert key in item, "{0} 缺 {1}".format(item.get("fixture_id"), key)
        for key in ("implicit_observed", "explicit_observed", "grade",
                    "implicit_fail_targets", "explicit_fail_targets"):
            assert key in item["expected"], (
                "{0}.expected 缺 {1}".format(item["fixture_id"], key))
        assert base64.b64decode(item["bytes_b64"]), (
            "{0} 的字节为空".format(item["fixture_id"]))


# ------------------------------------------------------------------ 零政策字面量门
#: 规则库里出现的、**不得抄进代码**的字段名/容器键/取值串（M1 规则库 + M2 解析通路）。
#: 这些只能来自 data/rules/**、data/mapping/** 与 data/parse/**，不得成为引擎源码里的
#: "第二份真相"。M2 新增项：附录 E 载荷的**内层要素键**与标签枚举值——解析器只能
#: 靠映射表别名识别它们，不许在 ``parse/`` 里硬编码。
FORBIDDEN_POLICY_TOKENS = (
    # 国标字段名（隐式标识要素）
    "content_property",
    "content_producer",
    "content_propagator",
    "propagate_id",
    # 附录 E 规定的容器键名
    "ContentProducer",
    "ProduceID",
    "ContentPropagator",
    "PropagateID",
    "AIGC:Label",
    "AIGC:ContentProducer",
    "AIGC:ProduceID",
    # 附录 E 载荷内层要素键（M2 解析通路必须从映射表别名识别，不得硬编码）
    "ReservedCode1",
    "ReservedCode2",
    "PropagatorID",
    # 显式标识要素 id
    "text_explicit_notice",
    "image_explicit_notice",
    "audio_explicit_notice",
    "video_explicit_notice",
    # 办法独有义务的目标 id（M2 适用性画像建立；同样只能来自规则库数据）
    "exported_file_explicit_label",
    "propagation_platform_hint",
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


def test_policy_token_gate_has_positive_control():
    """**阳性对照**：确认门本身能命中（否则可能是空验）。"""
    sample = "content_producer"
    assert any(t in sample for t in FORBIDDEN_POLICY_TOKENS), "门禁 token 集失效"


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
