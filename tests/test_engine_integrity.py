"""完整性判定与分级测试（含"元数据被剥离但显式标识在"的边界情形）。"""

import pytest

from labelcheck.engine import check_card, grade_findings
from labelcheck.model import (
    GRADE_COMPLIANT, GRADE_NON_COMPLIANT, GRADE_NOT_ASSESSED, GRADE_PARTIAL,
    Finding, LabelCard,
)

from _support import build_data_dir, make_card, make_mapping_field, make_rule


def _finding(status, severity="major", target="t", code="c"):
    return Finding("implicit", target, status, code=code, severity=severity)


# ------------------------------------------------------------------ 纯分级函数
def test_no_findings_is_not_assessed():
    assert grade_findings([])[0] == GRADE_NOT_ASSESSED


def test_all_pass_is_compliant():
    findings = [_finding("pass"), _finding("pass")]
    grade, missing, errors = grade_findings(findings)
    assert grade == GRADE_COMPLIANT
    assert missing == [] and errors == []


def test_unknown_only_is_partial():
    """无明确违规但有待人工确认 → partial（不是 compliant）。"""
    grade, _, _ = grade_findings([_finding("pass"), _finding("unknown")])
    assert grade == GRADE_PARTIAL


def test_minor_fail_is_partial():
    grade, missing, errors = grade_findings([
        _finding("pass"),
        _finding("fail", severity="minor", target="content_id", code="field_absent"),
    ])
    assert grade == GRADE_PARTIAL
    assert missing == ["content_id"]
    assert errors == ["field_absent"]


def test_major_fail_is_non_compliant():
    grade, _, _ = grade_findings([_finding("fail", severity="major")])
    assert grade == GRADE_NON_COMPLIANT


def test_critical_fail_is_non_compliant():
    grade, _, _ = grade_findings([_finding("fail", severity="critical")])
    assert grade == GRADE_NON_COMPLIANT


def test_skipped_does_not_affect_grade():
    grade, _, _ = grade_findings([_finding("pass"), _finding("skipped")])
    assert grade == GRADE_COMPLIANT


def test_missing_and_errors_are_deduplicated_and_ordered():
    findings = [
        _finding("fail", target="a", code="field_absent"),
        _finding("fail", target="b", code="format_mismatch"),
        _finding("fail", target="a", code="field_absent"),
    ]
    _, missing, errors = grade_findings(findings)
    assert missing == ["a", "b"]
    assert errors == ["field_absent", "format_mismatch"]


# ------------------------------------------------------------------ 端到端分级
@pytest.fixture
def run(tmp_path):
    def _run(rules, mapping_fields=None, **card_overrides):
        data = build_data_dir(
            tmp_path / "d",
            {"doc": {"version": "2025-09-01", "status": "verified", "rules": rules}},
            mapping_fields=mapping_fields,
        )
        card = LabelCard.from_dict(make_card(**card_overrides))
        return check_card(card, data)

    return _run


def test_fully_labeled_card_is_compliant(run):
    report = run(
        [make_rule("r-exp", scope="explicit", carrier=["text"], target="notice",
                   check_type="presence", status="verified"),
         make_rule("r-imp", scope="implicit", target="content_property",
                   check_type="presence", status="verified")],
        mapping_fields=[make_mapping_field("content_property", ["content.property"], status="verified")],
        explicit=[{"element": "notice", "present": True}],
        implicit={"content.property": "AI_GENERATED"},
    )
    assert report.grade == GRADE_COMPLIANT
    assert report.missing == []


def test_metadata_stripped_but_explicit_present_boundary(run):
    """边界情形（01 §三.3 显式要求）：元数据被剥离但显式标识在。

    隐式 critical 字段缺失 → non_compliant，且 missing 列出被剥离字段；
    显式判定仍全部 pass（证明两个 scope 的结果互不污染）。
    """
    report = run(
        [make_rule("r-exp", scope="explicit", carrier=["text"], target="notice",
                   check_type="presence", status="verified"),
         make_rule("r-imp", scope="implicit", target="content_property",
                   check_type="presence", severity="critical", status="verified")],
        mapping_fields=[make_mapping_field("content_property", ["content.property"], status="verified")],
        explicit=[{"element": "notice", "present": True}],
        implicit={},  # 元数据被剥离
    )
    assert [f.status for f in report.explicit] == ["pass"]
    assert [f.status for f in report.implicit] == ["fail"]
    assert report.grade == GRADE_NON_COMPLIANT
    assert "content_property" in report.missing


def test_metadata_stripped_minor_only_is_partial(run):
    """元数据剥离但只有 minor 级隐式规则 → partial（分级随严重度，不是一刀切）。"""
    report = run(
        [make_rule("r-imp", scope="implicit", target="content_property",
                   check_type="presence", severity="minor", status="verified")],
        mapping_fields=[make_mapping_field("content_property", ["content.property"], status="verified")],
        implicit={},
    )
    assert report.grade == GRADE_PARTIAL


def test_explicit_wrong_position_yields_partial(run):
    report = run(
        [make_rule("r-exp", scope="explicit", carrier=["text"], target="notice",
                   check_type="position", params={"allowed": ["head"]},
                   severity="major", status="verified")],
        explicit=[{"element": "notice", "present": True, "position": "tail"}],
    )
    assert report.grade == GRADE_NON_COMPLIANT
    assert report.errors == ["position_not_allowed"]
