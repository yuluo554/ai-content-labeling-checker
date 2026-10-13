"""隐式标识字段核验引擎测试（映射归一 + check_type 分派 + 门控）。"""

import pytest

from labelcheck.engine import check_card
from labelcheck.model import GRADE_NOT_ASSESSED, LabelCard

from _support import build_data_dir, make_mapping_field, make_card, make_rule


@pytest.fixture
def run(tmp_path):
    """在临时数据目录里跑一件标识卡（可自定义映射表）。"""

    def _run(rules, mapping_fields=None, doc_status="verified", **card_overrides):
        data = build_data_dir(
            tmp_path / "d",
            {"doc": {"version": "2025-09-01", "status": doc_status, "rules": rules}},
            mapping_fields=mapping_fields,
        )
        card = LabelCard.from_dict(make_card(**card_overrides))
        return check_card(card, data)

    return _run


PROP = [make_mapping_field("content_property", ["content.property"], status="verified")]


# ------------------------------------------------------------------ presence
def test_field_present_via_alias(run):
    report = run(
        [make_rule("r", scope="implicit", target="content_property",
                   check_type="presence", status="verified")],
        mapping_fields=PROP,
        implicit={"content.property": "AI_GENERATED"},
    )
    assert report.implicit[0].status == "pass"
    assert report.implicit[0].evidence["observed_key"] == "content.property"


def test_field_absent_fails_presence_rule(run):
    report = run(
        [make_rule("r", scope="implicit", target="content_property",
                   check_type="presence", status="verified")],
        mapping_fields=PROP,
        implicit={},
    )
    finding = report.implicit[0]
    assert finding.status == "fail"
    assert finding.code == "field_absent"


def test_field_absent_is_unknown_for_non_presence_rule(run):
    report = run(
        [make_rule("r", scope="implicit", target="content_property",
                   check_type="pattern", params={"regex": "^AI_"},
                   status="verified")],
        mapping_fields=PROP,
        implicit={},
    )
    finding = report.implicit[0]
    assert finding.status == "unknown"
    assert finding.code == "field_absent_cannot_verify"


# ------------------------------------------------------------------ pattern / enum / type / range
def test_pattern_pass_and_fail(run):
    rules = [make_rule("r", scope="implicit", target="service_provider_code",
                       check_type="pattern", params={"regex": "^SYN-[0-9]{4}$"},
                       status="verified")]
    mapping = [make_mapping_field("service_provider_code", ["service.provider.code"], status="verified")]

    ok = run(rules, mapping_fields=mapping, implicit={"service.provider.code": "SYN-0001"})
    assert ok.implicit[0].status == "pass"

    bad = run(rules, mapping_fields=mapping, implicit={"service.provider.code": "bad code!"})
    assert bad.implicit[0].status == "fail"
    assert bad.implicit[0].code == "format_mismatch"


def test_type_mismatch(run):
    report = run(
        [make_rule("r", scope="implicit", target="content_property",
                   check_type="type", params={"expect": "string"}, status="verified")],
        mapping_fields=PROP,
        implicit={"content.property": 12345},
    )
    assert report.implicit[0].code == "type_mismatch"


def test_range_out_of_bounds(run):
    report = run(
        [make_rule("r", scope="implicit", target="content_property",
                   check_type="range", params={"min": 0, "max": 100}, status="verified")],
        mapping_fields=PROP,
        implicit={"content.property": 101},
    )
    assert report.implicit[0].code == "value_out_of_range"


def test_range_in_bounds(run):
    report = run(
        [make_rule("r", scope="implicit", target="content_property",
                   check_type="range", params={"min": 0, "max": 100}, status="verified")],
        mapping_fields=PROP,
        implicit={"content.property": 100},
    )
    assert report.implicit[0].status == "pass"


# ------------------------------------------------------------------ 别名歧义记录
def test_alternatives_recorded_in_evidence(run):
    """多别名同时命中时，其余键记入 evidence.alternatives（不静默丢弃）。"""
    report = run(
        [make_rule("r", scope="implicit", target="content_property",
                   check_type="presence", status="verified")],
        mapping_fields=[make_mapping_field("content_property", ["k1", "k2"], status="verified")],
        implicit={"k1": "A", "k2": "B"},
    )
    evidence = report.implicit[0].evidence
    assert evidence["observed_key"] == "k1"
    assert evidence["alternatives"] == ["k2"]


# ------------------------------------------------------------------ 映射表缺陷
def test_rule_referencing_field_not_in_mapping_is_unknown(run):
    """规则引用了映射表里没有的国标字段 → unknown（数据缺陷，不计违规）。"""
    report = run(
        [make_rule("r", scope="implicit", target="nonexistent_field",
                   check_type="presence", status="verified")],
        mapping_fields=PROP,
        implicit={},
    )
    finding = report.implicit[0]
    assert finding.status == "unknown"
    assert finding.code == "field_not_in_mapping"


# ------------------------------------------------------------------ 载体门控 + 未评估
def test_implicit_carrier_gate(run):
    report = run(
        [make_rule("r", scope="implicit", carrier=["image"], target="content_property",
                   check_type="presence", status="verified")],
        mapping_fields=PROP,
        carrier="text",
        implicit={},
    )
    assert report.implicit == []


def test_pending_implicit_rules_do_not_run(run):
    report = run(
        [make_rule("r", scope="implicit", target="content_property",
                   check_type="presence", status="pending")],
        mapping_fields=PROP,
        implicit={},
    )
    assert report.implicit == []
    assert report.grade == GRADE_NOT_ASSESSED
