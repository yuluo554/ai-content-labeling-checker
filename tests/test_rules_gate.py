"""规则库门控测试（NFR-4 的唯一实现点）——**本文件是全项目最重要的纪律测试**。

断言：
1. ``pending`` 条目**绝不**进入 ``effective_ruleset().effective``；
2. 文档级 ``pending`` 会让该文档**全部**条目失效（双重门控）；
3. 仓库随附的 M0 规则库（全 pending）→ ``effective`` 为空；
4. 结构缺陷（缺 clause/source_url、坏 check_type、重复 id、指纹不符）**大声失败**。
"""

import pytest

from labelcheck.errors import RulesetError
from labelcheck.jsonio import canonical_json, sha256_text, write_json
from labelcheck.rules import STATUS_PENDING, STATUS_VERIFIED, effective_ruleset, load_registry

from _support import build_data_dir, make_rule


def _doc(rules, status="verified", version="2025-09-01", **kwargs):
    spec = {"version": version, "status": status, "rules": rules}
    spec.update(kwargs)
    return {"sample-doc": spec}


# ------------------------------------------------------------ 正向：生效路径
def test_verified_doc_and_rule_is_effective(tmp_path):
    rules = [make_rule("r1", status="verified")]
    data = build_data_dir(tmp_path / "d", _doc(rules, status="verified"))
    ruleset = effective_ruleset(data)
    assert ruleset.verified_rule_count == 1
    assert ruleset.pending_rule_count == 0
    assert ruleset.effective[0].rule_id == "r1"


def test_pending_rule_excluded_from_effective(tmp_path):
    """条目级 pending：文档 verified 但条目 pending → 不得生效。"""
    rules = [
        make_rule("r-verified", status="verified"),
        make_rule("r-pending", status="pending"),
    ]
    data = build_data_dir(tmp_path / "d", _doc(rules, status="verified"))
    ruleset = effective_ruleset(data)

    ids = [r.rule_id for r in ruleset.effective]
    assert ids == ["r-verified"]
    assert "r-pending" not in ids
    assert [r.rule_id for r in ruleset.pending] == ["r-pending"]
    assert ruleset.pending_rule_count == 1


def test_pending_document_invalidates_all_its_rules(tmp_path):
    """文档级 pending：即使条目自报 verified，也一律不得生效。"""
    rules = [make_rule("r1", status="verified")]
    data = build_data_dir(tmp_path / "d", _doc(rules, status="pending"))
    ruleset = effective_ruleset(data)

    assert ruleset.effective == []
    assert [r.rule_id for r in ruleset.pending] == ["r1"]


def test_gate_is_all_or_nothing_per_document(tmp_path):
    """多文档混合：只有 verified 文档的 verified 条目生效。"""
    verified_rules = [make_rule("good", status="verified")]
    pending_rules = [make_rule("bad", status="verified")]
    data = build_data_dir(tmp_path / "d", {
        "doc-a": {"version": "2025-09-01", "status": "verified", "rules": verified_rules},
        "doc-b": {"version": "2025-09-01", "status": "pending", "rules": pending_rules},
    })
    ruleset = effective_ruleset(data)

    assert [r.rule_id for r in ruleset.effective] == ["good"]
    assert [r.rule_id for r in ruleset.pending] == ["bad"]
    assert ruleset.coordinate == "doc-a@2025-09-01+doc-b@2025-09-01"


def test_rules_for_filters_scope_and_carrier(tmp_path):
    rules = [
        make_rule("t", scope="explicit", carrier=["text"], target="e1", status="verified"),
        make_rule("i", scope="implicit", carrier=[], target="content_property", status="verified"),
        make_rule("img", scope="explicit", carrier=["image"], target="e2", status="verified"),
    ]
    data = build_data_dir(tmp_path / "d", _doc(rules, status="verified"))
    ruleset = effective_ruleset(data)

    text_explicit = [r.rule_id for r in ruleset.rules_for("explicit", "text")]
    assert text_explicit == ["t"]
    implicit_any = [r.rule_id for r in ruleset.rules_for("implicit", "video")]
    assert implicit_any == ["i"]


# ------------------------------------------------------------ 仓库真实数据
def test_shipped_ruleset_matches_verified_documents(data_dir):
    """M1 随附规则库：GB 45438-2025 已核对 → 生效条目非空；办法条目待在 pending。

    门控语义本身（pending 不进 effective）由上方临时数据用例锁死；此处只断言
    随附数据的**可观测结果**与文档 status 一致（双重门控的集成证据）。
    """
    from labelcheck.jsonio import load_json
    registry = load_json(data_dir / "rules" / "registry.json")
    doc_status = {d["doc_id"]: d["status"] for d in registry["documents"]}

    ruleset = effective_ruleset(data_dir)
    assert ruleset.verified_rule_count > 0, "M1 后应有已核对生效的规则"
    assert ruleset.coordinate == "labeling-measures@2025-09-01+gb45438-2025@2025-09-01"

    doc_ids = [d["doc_id"] for d in ruleset.doc_versions]
    assert doc_ids == ["labeling-measures", "gb45438-2025"]

    # 生效条目只能来自 status=verified 的文档
    for rule in ruleset.effective:
        assert doc_status[rule.doc_id] == "verified", (
            "pending 文档的条目进入了判定路径：{0}".format(rule.rule_id))
        assert rule.status == "verified"

    # 每个 pending 条目都不得出现在 effective 中
    effective_ids = set(r.rule_id for r in ruleset.effective)
    for rule in ruleset.pending:
        assert rule.rule_id not in effective_ids, (
            "pending 条目进入了 effective：{0}".format(rule.rule_id))


# ------------------------------------------------------------ 结构校验（必须大声失败）
def test_verified_rule_without_article_is_rejected(tmp_path):
    rule = make_rule("r1", status="verified")
    rule["clause"] = {}
    data = build_data_dir(tmp_path / "d", _doc([rule], status="verified"))
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "clause.article" in str(excinfo.value)


def test_verified_rule_without_source_url_is_rejected(tmp_path):
    rule = make_rule("r1", status="verified", source_url="")
    data = build_data_dir(tmp_path / "d", _doc([rule], status="verified"))
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "source_url" in str(excinfo.value)


def test_bad_check_type_is_rejected(tmp_path):
    rule = make_rule("r1", check_type="telepathy", status="pending")
    data = build_data_dir(tmp_path / "d", _doc([rule], status="pending"))
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "check_type" in str(excinfo.value)


def test_bad_status_is_rejected(tmp_path):
    rule = make_rule("r1", status="probably-fine")
    data = build_data_dir(tmp_path / "d", _doc([rule], status="pending"))
    with pytest.raises(RulesetError):
        effective_ruleset(data)


def test_duplicate_rule_ids_rejected(tmp_path):
    rules = [make_rule("dup"), make_rule("dup")]
    data = build_data_dir(tmp_path / "d", _doc(rules, status="pending"))
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "重复" in str(excinfo.value)


def test_position_rule_requires_allowed_list(tmp_path):
    rule = make_rule("r1", check_type="position", params={})
    data = build_data_dir(tmp_path / "d", _doc([rule], status="pending"))
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "allowed" in str(excinfo.value)


def test_pattern_rule_requires_regex(tmp_path):
    rule = make_rule("r1", check_type="pattern", params={})
    data = build_data_dir(tmp_path / "d", _doc([rule], status="pending"))
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "regex" in str(excinfo.value)


def test_rule_doc_id_mismatch_rejected(tmp_path):
    """规则文件里的 doc_id 与注册表不一致必须报错，不能静默错配。"""
    data = build_data_dir(tmp_path / "d", _doc([make_rule("r1")], status="pending"))
    path = data / "rules" / "sample-doc" / "2025-09-01.json"
    payload = {"schema_version": 1, "doc_id": "WRONG", "version": "2025-09-01", "rules": []}
    write_json(path, payload)
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "doc_id" in str(excinfo.value)


def test_registry_sha256_mismatch_rejected(tmp_path):
    """注册表登记的指纹与文件实际内容不符 → 大声失败（数据真伪门）。"""
    rules = [make_rule("r1", status="verified")]
    data = build_data_dir(
        tmp_path / "d", _doc(rules, status="verified", sha256="deadbeef" + "0" * 56)
    )
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "指纹" in str(excinfo.value) or "sha256" in str(excinfo.value)


def test_registry_sha256_consistent_passes(tmp_path):
    """登记值正确时必须通过（证明上条不是"永远报错"）。"""
    rules = [make_rule("r1", status="verified")]
    payload = {"schema_version": 1, "doc_id": "sample-doc", "version": "2025-09-01", "rules": rules}
    expected = sha256_text(canonical_json(payload, indent=None, sort_keys=True))
    data = build_data_dir(tmp_path / "d", _doc(rules, status="verified", sha256=expected))
    ruleset = effective_ruleset(data)
    assert ruleset.verified_rule_count == 1
    assert ruleset.doc_versions[0]["sha256"] == expected


def test_registry_missing_active_version_is_warning_not_crash(tmp_path):
    rules = [make_rule("r1", status="verified")]
    data = build_data_dir(
        tmp_path / "d",
        _doc(rules, status="verified"),
        active={"sample-doc": "1999-01-01"},
    )
    ruleset = effective_ruleset(data)
    assert ruleset.effective == []
    assert ruleset.warnings, "active 指向缺失版本时应有警告，不静默"


def test_load_registry_rejects_unknown_active_doc(tmp_path):
    data = build_data_dir(tmp_path / "d", _doc([], status="pending"))
    registry = {
        "schema_version": 1,
        "documents": [{
            "doc_id": "sample-doc",
            "status": "pending",
            "versions": [{"version": "2025-09-01", "rules_file": "sample-doc/2025-09-01.json"}],
        }],
        "active": {"nope": "2025-09-01"},
    }
    write_json(data / "rules" / "registry.json", registry)
    with pytest.raises(RulesetError) as excinfo:
        load_registry(data)
    assert "未注册" in str(excinfo.value)


# ------------------------------------------------------------ 场景门控（M2 适用性画像）
def test_rule_with_known_scenario_loads(tmp_path):
    """only_if.scenario 声明已知场景 → 正常加载，且 Rule.scenarios 可读。"""
    rule = make_rule("r", scope="explicit", target="t", check_type="presence",
                     status="verified", only_if={"scenario": ["exported"]})
    data = build_data_dir(tmp_path / "d", _doc([rule], status="verified"))
    ruleset = effective_ruleset(data)
    assert ruleset.effective[0].scenarios == ["exported"]
    assert ruleset.effective[0].applies_to_scenario("exported")
    assert not ruleset.effective[0].applies_to_scenario("authored")


def test_rule_with_unknown_scenario_is_rejected(tmp_path):
    """未知场景必须大声失败——否则场景门控会静默失效（规则永不生效）。"""
    rule = make_rule("r", scope="explicit", target="t", check_type="presence",
                     status="verified", only_if={"scenario": ["telepathy"]})
    data = build_data_dir(tmp_path / "d", _doc([rule], status="verified"))
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "scenario" in str(excinfo.value)


def test_rule_with_non_list_scenario_rejected(tmp_path):
    rule = make_rule("r", scope="explicit", target="t", check_type="presence",
                     status="verified", only_if={"scenario": "exported"})
    data = build_data_dir(tmp_path / "d", _doc([rule], status="verified"))
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "scenario" in str(excinfo.value)


def test_unique_rule_must_be_implicit_scope(tmp_path):
    """unique 依赖整块隐式标识上下文 → 只许 implicit scope。"""
    rule = make_rule("r", scope="explicit", target="t", check_type="unique",
                     status="verified")
    data = build_data_dir(tmp_path / "d", _doc([rule], status="verified"))
    with pytest.raises(RulesetError) as excinfo:
        effective_ruleset(data)
    assert "unique" in str(excinfo.value)


def test_rules_for_card_splits_applicable_and_skipped(tmp_path):
    """rules_for_card 是适用性画像的单一查询点：返回 (applicable, skipped)。"""
    rules = [
        make_rule("r-any", scope="implicit", target="a", check_type="presence",
                  status="verified"),
        make_rule("r-exp", scope="implicit", target="b", check_type="presence",
                  status="verified", only_if={"scenario": ["exported"]}),
    ]
    data = build_data_dir(tmp_path / "d", _doc(rules, status="verified"))
    ruleset = effective_ruleset(data)

    applicable, skipped = ruleset.rules_for_card("implicit", "text", "authored")
    assert [r.rule_id for r in applicable] == ["r-any"]
    assert [r.rule_id for r in skipped] == ["r-exp"]

    applicable, skipped = ruleset.rules_for_card("implicit", "text", "exported")
    assert [r.rule_id for r in applicable] == ["r-any", "r-exp"]
    assert skipped == []
