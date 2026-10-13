"""端到端编排（**单一事实源**）：CLI 与未来 GUI 共用同一编排，不各起一套行为。

契约见 plan/03 §一 / plan/04 §一。GUI 只渲染本模块返回的 :class:`CheckReport`。
"""

from ..mapping import load_mapping_table
from ..model import CheckReport, LabelCard
from ..rules import effective_ruleset
from .explicit import check_explicit
from .implicit import check_implicit
from .integrity import grade_findings


def check_card(card, data_dir, generated_at=""):
    """对单件标识卡做全链路核验，返回 :class:`CheckReport`。

    :param card: :class:`LabelCard`（已通过 ``from_dict`` 校验）
    :param data_dir: 数据目录（规则库 + 映射表所在）
    :param generated_at: 报告时间戳，**由调用方传入**（基准/测试传固定值 →
        相同输入两次导出逐字节一致）
    """
    ruleset = effective_ruleset(data_dir)
    mapping_table = load_mapping_table(data_dir)

    explicit_findings = check_explicit(card, ruleset)
    implicit_findings = check_implicit(card, ruleset, mapping_table)

    findings = explicit_findings + implicit_findings
    grade, missing, errors = grade_findings(findings)

    return CheckReport(
        card_id=card.card_id,
        carrier=card.carrier,
        ruleset_coordinate=ruleset.coordinate,
        documents=ruleset.doc_versions,
        verified_rule_count=ruleset.verified_rule_count,
        pending_rule_count=ruleset.pending_rule_count,
        explicit=explicit_findings,
        implicit=implicit_findings,
        grade=grade,
        missing=missing,
        errors=errors,
        content_sha256=card.content_sha256,
        generated_at=generated_at,
    )


def check_card_dict(card_data, data_dir, generated_at=""):
    """从 dict 校验并核验（CLI 主通路）。"""
    card = LabelCard.from_dict(card_data)
    return check_card(card, data_dir, generated_at=generated_at)


__all__ = ["check_card", "check_card_dict"]
