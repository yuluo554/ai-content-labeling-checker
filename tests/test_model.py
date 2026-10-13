"""数据模型测试：LabelCard 输入校验、Finding/CheckReport 语义。"""

import pytest

from labelcheck.errors import InputError
from labelcheck.model import (
    CheckReport, Finding, LabelCard,
    STATUS_FAIL, STATUS_PASS, STATUS_UNKNOWN, STATUS_SKIPPED,
)

from _support import make_card


# ------------------------------------------------------------------ LabelCard 校验
def test_valid_card_roundtrip():
    card = LabelCard.from_dict(make_card())
    assert card.card_id == "SYN-TEST-0001"
    assert card.carrier == "text"
    assert card.to_dict()["content_sha256"] == "a" * 64


def test_card_must_be_object():
    with pytest.raises(InputError):
        LabelCard.from_dict(["not", "an", "object"])


def test_card_requires_card_id():
    with pytest.raises(InputError) as excinfo:
        LabelCard.from_dict(make_card(card_id=""))
    assert "card_id" in str(excinfo.value)


def test_card_rejects_unknown_carrier():
    with pytest.raises(InputError) as excinfo:
        LabelCard.from_dict(make_card(carrier="hologram"))
    assert "carrier" in str(excinfo.value)


@pytest.mark.parametrize("carrier", ["text", "image", "audio", "video"])
def test_card_accepts_all_declared_carriers(carrier):
    card = LabelCard.from_dict(make_card(carrier=carrier))
    assert card.carrier == carrier


def test_card_requires_valid_sha256():
    with pytest.raises(InputError) as excinfo:
        LabelCard.from_dict(make_card(content_sha256="XYZ"))
    assert "content_sha256" in str(excinfo.value)


def test_card_rejects_uppercase_sha256():
    with pytest.raises(InputError):
        LabelCard.from_dict(make_card(content_sha256="A" * 64))


def test_card_rejects_short_sha256():
    with pytest.raises(InputError):
        LabelCard.from_dict(make_card(content_sha256="a" * 63))


def test_card_rejects_bad_source():
    with pytest.raises(InputError) as excinfo:
        LabelCard.from_dict(make_card(source="telepathy"))
    assert "source" in str(excinfo.value)


def test_card_rejects_non_list_explicit():
    with pytest.raises(InputError):
        LabelCard.from_dict(make_card(explicit={"element": "x"}))


def test_card_rejects_explicit_item_without_element():
    with pytest.raises(InputError) as excinfo:
        LabelCard.from_dict(make_card(explicit=[{"present": True}]))
    assert "element" in str(excinfo.value)


def test_card_rejects_non_dict_implicit():
    with pytest.raises(InputError):
        LabelCard.from_dict(make_card(implicit=["x"]))


def test_card_rejects_non_string_notes():
    with pytest.raises(InputError):
        LabelCard.from_dict(make_card(notes=123))


def test_card_defaults_are_safe():
    card = LabelCard.from_dict(make_card())
    assert card.explicit == []
    assert card.implicit == {}


def test_find_explicit_returns_first_match():
    card = LabelCard.from_dict(make_card(explicit=[
        {"element": "a", "present": True},
        {"element": "b", "present": False},
    ]))
    assert card.find_explicit("b")["present"] is False
    assert card.find_explicit("zzz") is None


# ------------------------------------------------------------------ Finding
def test_finding_rejects_bad_status():
    with pytest.raises(ValueError):
        Finding("explicit", "t", "maybe")


def test_finding_violation_semantics():
    """unknown 不计违规但需人工确认（关键语义，不许漂移）。"""
    fail = Finding("explicit", "t", STATUS_FAIL)
    unknown = Finding("explicit", "t", STATUS_UNKNOWN)
    passed = Finding("explicit", "t", STATUS_PASS)
    skipped = Finding("explicit", "t", STATUS_SKIPPED)

    assert fail.is_violation and not fail.needs_review
    assert not unknown.is_violation and unknown.needs_review
    assert not passed.is_violation and not passed.needs_review
    assert not skipped.is_violation and not skipped.needs_review


def test_finding_to_dict_contains_contract_fields():
    finding = Finding("implicit", "content_property", STATUS_FAIL, code="field_absent",
                      clause={"article": "第9条"}, evidence={"observed": None}, severity="critical")
    payload = finding.to_dict()
    for key in ("scope", "target", "status", "severity", "code", "message", "clause", "evidence"):
        assert key in payload
    assert payload["severity"] == "critical"


def test_finding_rejects_bad_severity():
    with pytest.raises(ValueError):
        Finding("implicit", "t", STATUS_FAIL, severity="catastrophic")


# ------------------------------------------------------------------ CheckReport
def test_report_has_violation_and_disclaimer():
    report = CheckReport(
        card_id="c1", carrier="text",
        explicit=[Finding("explicit", "t", STATUS_FAIL)],
        implicit=[Finding("implicit", "f", STATUS_UNKNOWN)],
    )
    assert report.has_violation
    assert len(report.violations) == 1
    assert len(report.reviews) == 1
    assert "供参考" in report.disclaimer
    assert "规避" in report.disclaimer, "免责声明必须含'不提供标识规避'口径"


def test_report_without_violation():
    report = CheckReport(card_id="c1", carrier="text",
                         explicit=[Finding("explicit", "t", STATUS_PASS)])
    assert not report.has_violation
    assert report.violations == []


def test_report_all_findings_order_explicit_first():
    e = Finding("explicit", "e1", STATUS_PASS)
    i = Finding("implicit", "i1", STATUS_PASS)
    report = CheckReport(card_id="c1", carrier="text", explicit=[e], implicit=[i])
    assert report.all_findings == [e, i]


def test_report_to_dict_shape():
    report = CheckReport(card_id="c1", carrier="text", ruleset_coordinate="d@2025-09-01")
    payload = report.to_dict()
    assert payload["ruleset"]["coordinate"] == "d@2025-09-01"
    assert payload["disclaimer"]
    assert set(["ruleset", "explicit", "implicit", "grade", "missing", "errors"]).issubset(payload)
