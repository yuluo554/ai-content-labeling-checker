"""显式标识核验引擎测试（含位置/形式判定 FR-2 与"缺值不臆测"纪律）。"""

import pytest

from labelcheck.engine import check_card
from labelcheck.model import GRADE_NOT_ASSESSED, LabelCard

from _support import build_data_dir, make_card, make_rule


@pytest.fixture
def run(tmp_path):
    """在临时数据目录里跑一件标识卡，返回 :class:`CheckReport`。"""

    def _run(rules, doc_status="verified", **card_overrides):
        data = build_data_dir(tmp_path / "d", {
            "doc": {"version": "2025-09-01", "status": doc_status, "rules": rules},
        })
        card = LabelCard.from_dict(make_card(**card_overrides))
        return check_card(card, data)

    return _run


# ------------------------------------------------------------------ presence
def test_presence_pass_when_element_present(run):
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="presence", status="verified")],
        explicit=[{"element": "e1", "present": True}],
    )
    assert [f.status for f in report.explicit] == ["pass"]


def test_presence_fail_when_element_absent(run):
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="presence", status="verified")],
        explicit=[],
    )
    finding = report.explicit[0]
    assert finding.status == "fail"
    assert finding.code == "element_absent"


def test_presence_fail_when_declared_not_present(run):
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="presence", status="verified")],
        explicit=[{"element": "e1", "present": False}],
    )
    assert report.explicit[0].code == "element_not_present"


# ------------------------------------------------------------------ position（FR-2）
def test_position_pass_when_allowed(run):
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="position", params={"allowed": ["head", "tail"]},
                   status="verified")],
        explicit=[{"element": "e1", "present": True, "position": "head"}],
    )
    assert report.explicit[0].status == "pass"


def test_position_fail_when_not_allowed(run):
    """不只判"有没有"，还判"位置对不对"——这是 FR-2 的核心。"""
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="position", params={"allowed": ["head", "tail"]},
                   status="verified")],
        explicit=[{"element": "e1", "present": True, "position": "middle-of-nowhere"}],
    )
    finding = report.explicit[0]
    assert finding.status == "fail"
    assert finding.code == "position_not_allowed"


def test_position_unknown_when_position_missing(run):
    """要素在但没记位置 → unknown，不得猜成合规。"""
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="position", params={"allowed": ["head"]},
                   status="verified")],
        explicit=[{"element": "e1", "present": True}],
    )
    finding = report.explicit[0]
    assert finding.status == "unknown"
    assert finding.code == "position_unknown"


def test_position_rule_element_absent_is_unknown_not_fail(run):
    """非 presence 类型 + 要素缺失 → unknown（缺值不臆测）。"""
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="position", params={"allowed": ["head"]},
                   status="verified")],
        explicit=[],
    )
    finding = report.explicit[0]
    assert finding.status == "unknown"
    assert finding.code == "element_absent_cannot_verify"


def test_element_presence_unknown_when_present_flag_missing(run):
    """present 字段缺失 → unknown（不假设存在也不假设不存在）。"""
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="presence", status="verified")],
        explicit=[{"element": "e1"}],
    )
    assert report.explicit[0].code == "element_presence_unknown"
    assert report.explicit[0].status == "unknown"


# ------------------------------------------------------------------ 载体门控
def test_carrier_gate_excludes_other_carriers(run):
    """image 规则不得对 text 件生效（类目隔离）。"""
    report = run(
        [make_rule("r-img", scope="explicit", carrier=["image"], target="e1",
                   check_type="presence", status="verified")],
        carrier="text",
        explicit=[],
    )
    assert report.explicit == []


def test_empty_carrier_list_applies_to_all(run):
    report = run(
        [make_rule("r-any", scope="explicit", carrier=[], target="e1",
                   check_type="presence", status="verified")],
        carrier="video",
        explicit=[],
    )
    assert len(report.explicit) == 1


# ------------------------------------------------------------------ 未评估
def test_no_effective_rules_grade_is_not_assessed(run):
    """全 pending 规则 → not_assessed（绝不输出假合规）。"""
    report = run(
        [make_rule("r", scope="explicit", target="e1")],
        doc_status="pending",
    )
    assert report.grade == GRADE_NOT_ASSESSED
    assert report.explicit == []
    assert report.pending_rule_count == 1


def test_finding_carries_clause_reference(run):
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="presence", status="verified",
                   clause={"article": "第12条", "excerpt": "要点"})],
        explicit=[{"element": "e1", "present": True}],
    )
    assert report.explicit[0].clause["article"] == "第12条"


# ------------------------------------------------------------------ 其它 check_type
def test_enum_check_on_explicit_value(run):
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="enum", params={"allowed": ["AI_GENERATED", "AI_EDITED"]},
                   status="verified")],
        explicit=[{"element": "e1", "present": True, "value": "AI_GENERATED"}],
    )
    assert report.explicit[0].status == "pass"


def test_enum_check_fails_on_disallowed_value(run):
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="enum", params={"allowed": ["AI_GENERATED"]},
                   status="verified")],
        explicit=[{"element": "e1", "present": True, "value": "HUMAN"}],
    )
    assert report.explicit[0].code == "value_not_allowed"
