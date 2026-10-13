# -*- coding: utf-8 -*-
"""场景（适用性画像）与观测作用域测试（M2 新增语义）。

锁死三件事：

1. **场景门控**：``only_if.scenario`` 未命中 → ``skipped``（**不是 fail**）；
   命中的场景才参与判定。办法第四条第二款（导出）/第六条（传播）据此生效。
2. **观测作用域**：``observed[scope]=False`` → 该 scope 全部规则判 ``unknown``
   （解析通路看不到渲染后的显式标识），且报告如实暴露未观测作用域。
3. **门控边界**：不适用场景的条目**不得**产出 fail —— 这是"不冤枉用户"的落点。
"""

import pytest

from labelcheck.engine import check_card
from labelcheck.model import (
    GRADE_NON_COMPLIANT, GRADE_NOT_ASSESSED, GRADE_PARTIAL, LabelCard,
    SCENARIO_AUTHORED, SCENARIO_EXPORTED, SCENARIO_PROPAGATED,
)

from _support import build_data_dir, make_card, make_rule


@pytest.fixture
def run(tmp_path):
    def _run(rules, doc_status="verified", mapping_fields=None, **card_overrides):
        data = build_data_dir(
            tmp_path / "d",
            {"doc": {"version": "2025-09-01", "status": doc_status, "rules": rules}},
            mapping_fields=mapping_fields,
        )
        card = LabelCard.from_dict(make_card(**card_overrides))
        return check_card(card, data)

    return _run


# ------------------------------------------------------------------ 场景门控
def test_scenario_rule_skipped_when_not_applicable(run):
    """只适用 exported 的规则在 authored 场景下 → skipped（不是 fail）。"""
    report = run(
        [make_rule("r-export", scope="explicit", target="exported_file_explicit_label",
                   check_type="presence", status="verified",
                   only_if={"scenario": ["exported"]}, severity="major")],
        explicit=[],
        scenario=SCENARIO_AUTHORED,
    )
    finding = report.explicit[0]
    assert finding.status == "skipped"
    assert finding.code == "scenario_not_applicable"
    assert not report.has_violation, "场景不适用不得计为违规"
    # 唯一一条规则不适用 → 没有任何规则实际施加 → 未评估（"没检查"≠"合规"）
    assert report.grade == GRADE_NOT_ASSESSED


def test_scenario_skip_does_not_mask_other_findings(run):
    """既有 skipped 又有实际判定时，等级按实际判定给（skipped 不参与分级）。"""
    report = run(
        [
            make_rule("r-export", scope="explicit", target="exported_file_explicit_label",
                      check_type="presence", status="verified",
                      only_if={"scenario": ["exported"]}, severity="major"),
            make_rule("r-ok", scope="implicit", target="content_property",
                      check_type="presence", status="verified", severity="critical"),
        ],
        mapping_fields=[{"national_field": "content_property", "label": "x",
                         "aliases": ["AIGC:Label"], "status": "verified",
                         "source_url": "https://example.invalid/spec",
                         "clause": {"article": "第9条", "excerpt": "占位要点"}}],
        implicit={"AIGC:Label": "1"},
        scenario=SCENARIO_AUTHORED,
    )
    assert report.explicit[0].status == "skipped"
    assert report.implicit[0].status == "pass"
    assert report.grade == "compliant", "有一条实际判定 pass → 不是未评估"


def test_scenario_rule_applies_in_declared_scenario(run):
    """同一规则在 exported 场景下生效：要素缺失 → fail。"""
    report = run(
        [make_rule("r-export", scope="explicit", target="exported_file_explicit_label",
                   check_type="presence", status="verified",
                   only_if={"scenario": ["exported"]}, severity="major")],
        explicit=[],
        scenario=SCENARIO_EXPORTED,
    )
    finding = report.explicit[0]
    assert finding.status == "fail"
    assert finding.code == "element_absent"
    assert report.grade == GRADE_NON_COMPLIANT


def test_empty_scenario_declaration_applies_everywhere(run):
    """未声明场景的规则在所有场景下都适用（默认口径）。"""
    rules = [make_rule("r", scope="explicit", target="e1", check_type="presence",
                       status="verified")]
    for scenario in (SCENARIO_AUTHORED, SCENARIO_EXPORTED, SCENARIO_PROPAGATED):
        report = run(rules, explicit=[{"element": "e1", "present": True}], scenario=scenario)
        assert report.explicit[0].status == "pass", "场景 {0} 应适用".format(scenario)


def test_propagated_scenario_activates_propagation_rules(run):
    """传播场景下，传播要素缺失 → fail（办法第六条 / 国标 §6.1 a) 4) 5)）。"""
    report = run(
        [make_rule("r-prop", scope="implicit", target="content_propagator",
                   check_type="presence", status="verified",
                   only_if={"scenario": ["propagated"]}, severity="major")],
        mapping_fields=[{"national_field": "content_propagator", "label": "x",
                         "aliases": ["AIGC:Propagator"], "status": "verified",
                         "source_url": "https://example.invalid/spec",
                         "clause": {"article": "第9条", "excerpt": "占位要点"}}],
        implicit={},
        scenario=SCENARIO_PROPAGATED,
    )
    assert report.implicit[0].status == "fail"


def test_skipped_finding_records_scenario_and_applies_to(run):
    report = run(
        [make_rule("r-export", scope="explicit", target="t", check_type="presence",
                   status="verified", only_if={"scenario": ["exported"]})],
        scenario=SCENARIO_AUTHORED,
    )
    finding = report.explicit[0]
    assert finding.scenario == SCENARIO_AUTHORED
    assert finding.evidence["applies_to"] == ["exported"]


# ------------------------------------------------------------------ 观测作用域
def test_unobserved_explicit_scope_yields_unknown_not_fail(run):
    """显式作用域未观测 → unknown（不臆测"缺失"也不臆测"合规"）。"""
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="text_explicit_notice",
                   check_type="presence", status="verified", severity="major")],
        explicit=[],
        observed={"explicit": False, "implicit": True},
    )
    finding = report.explicit[0]
    assert finding.status == "unknown"
    assert finding.code == "explicit_not_observed"
    assert not report.has_violation, "未观测不得产生违规"
    assert report.unobserved_scopes == ["explicit"]


def test_unobserved_implicit_scope_yields_unknown(run):
    report = run(
        [make_rule("r", scope="implicit", target="content_property",
                   check_type="presence", status="verified", severity="critical")],
        mapping_fields=[{"national_field": "content_property", "label": "x",
                         "aliases": ["AIGC:Label"], "status": "verified",
                         "source_url": "https://example.invalid/spec",
                         "clause": {"article": "第9条", "excerpt": "占位要点"}}],
        implicit={},
        observed={"explicit": True, "implicit": False},
    )
    assert report.implicit[0].status == "unknown"
    assert report.implicit[0].code == "implicit_not_observed"
    assert report.unobserved_scopes == ["implicit"]


def test_observed_scope_behaves_normally(run):
    """已观测的 scope 照常判定（证明上面的 unknown 来自观测标记而非恒 unknown）。"""
    report = run(
        [make_rule("r", scope="explicit", carrier=["text"], target="e1",
                   check_type="presence", status="verified")],
        explicit=[{"element": "e1", "present": True}],
    )
    assert report.explicit[0].status == "pass"
    assert report.unobserved_scopes == []


# ------------------------------------------------------------------ 卡片契约
def test_card_defaults_scenario_and_observed():
    card = LabelCard.from_dict(make_card())
    assert card.scenario == SCENARIO_AUTHORED
    assert card.observed == {"explicit": True, "implicit": True}


def test_card_rejects_unknown_scenario():
    from labelcheck.errors import InputError
    with pytest.raises(InputError) as excinfo:
        LabelCard.from_dict(make_card(scenario="telepathy"))
    assert "scenario" in str(excinfo.value)


def test_card_rejects_unknown_observed_scope():
    from labelcheck.errors import InputError
    with pytest.raises(InputError) as excinfo:
        LabelCard.from_dict(make_card(observed={"telepathy": True}))
    assert "observed" in str(excinfo.value)


def test_card_rejects_non_bool_observed_value():
    from labelcheck.errors import InputError
    with pytest.raises(InputError):
        LabelCard.from_dict(make_card(observed={"explicit": "yes"}))


def test_report_payload_carries_scenario_and_observed(run):
    report = run([], scenario=SCENARIO_EXPORTED,
                 observed={"explicit": False, "implicit": True})
    payload = report.to_dict()
    assert payload["scenario"] == SCENARIO_EXPORTED
    assert payload["observed"] == {"explicit": False, "implicit": True}
