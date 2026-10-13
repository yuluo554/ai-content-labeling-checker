"""隐式标识（元数据）字段核验引擎（契约见 plan/04 §五）。

流程：``resolve_fields`` 把容器原始键归一为国标字段 → 对每条 ``scope=implicit``
生效规则判定存在性/类型/格式/取值。

**关键纪律**：
- 字段缺失：``presence`` 类判 ``fail``（``field_absent``）；其余类型判 ``unknown``；
- 有多个别名同时命中时，在 evidence 中记录 ``alternatives``（不静默丢弃）；
- **非生效（pending）规则不参与判定**——映射表与规则库同为门控对象。
"""

from ..mapping import resolve_fields
from ..model import STATUS_FAIL, STATUS_PASS, STATUS_UNKNOWN, Finding
from ..rules.rule import SCOPE_IMPLICIT, evaluate

CODE_FIELD_ABSENT = "field_absent"
CODE_FIELD_ABSENT_CANNOT_VERIFY = "field_absent_cannot_verify"


def _finding(rule, status, code, message, evidence=None):
    return Finding(
        scope=SCOPE_IMPLICIT,
        target=rule.target,
        status=status,
        code=code,
        message=message,
        clause=rule.clause,
        evidence=evidence,
        severity=rule.severity,
    )


def check_implicit(card, ruleset, mapping_table):
    """对隐式字段逐条核验，返回 :class:`Finding` 列表（顺序 = 规则加载序）。"""
    # 全表归一：规则未覆盖到的字段也解析，便于报告与调试
    resolutions = resolve_fields(card.implicit, mapping_table)

    findings = []
    for rule in ruleset.rules_for(SCOPE_IMPLICIT, card.carrier):
        resolution = resolutions.get(rule.target)
        if resolution is None:
            # 规则引用了映射表中不存在的国标字段 → 数据缺陷（不猜、不计违规）
            findings.append(_finding(
                rule, STATUS_UNKNOWN, "field_not_in_mapping",
                "规则引用的国标字段不在映射表中：{0}".format(rule.target),
                {"observed": None},
            ))
            continue

        evidence = {"observed_key": resolution.matched_key}
        if resolution.alternatives:
            evidence["alternatives"] = list(resolution.alternatives)

        if not resolution.found:
            if rule.check_type == "presence":
                findings.append(_finding(
                    rule, STATUS_FAIL, CODE_FIELD_ABSENT,
                    "隐式标识字段缺失：{0}".format(rule.target), evidence,
                ))
            else:
                findings.append(_finding(
                    rule, STATUS_UNKNOWN, CODE_FIELD_ABSENT_CANNOT_VERIFY,
                    "隐式字段缺失，无法核验其{0}约束：{1}".format(rule.check_type, rule.target),
                    evidence,
                ))
            continue

        if rule.check_type == "presence":
            status, code, message, extra = evaluate(rule, resolution.value)
            evidence.update(extra)
            findings.append(_finding(rule, status, code, message, evidence))
            continue

        status, code, message, extra = evaluate(rule, resolution.value)
        evidence.update(extra)
        findings.append(_finding(rule, status, code, message, evidence))

    return findings


__all__ = ["check_implicit", "CODE_FIELD_ABSENT", "CODE_FIELD_ABSENT_CANNOT_VERIFY"]
