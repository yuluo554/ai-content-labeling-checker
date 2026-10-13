"""隐式标识（元数据）字段核验引擎（契约见 plan/04 §五）。

流程：``resolve_fields`` 把容器原始键归一为国标字段 → 对每条 ``scope=implicit``
生效规则判定存在性/类型/格式/取值。

**关键纪律**：
- 字段缺失：``presence`` 类判 ``fail``（``field_absent``）；其余类型判 ``unknown``；
- 有多个别名同时命中时，在 evidence 中记录 ``alternatives``（不静默丢弃）；
- 场景不适用（``only_if.scenario`` 未命中）→ ``skipped``（不是 fail）；
- 隐式作用域未被观测（整块元数据都没有）→ 该 scope 全部规则判 ``unknown``
  （code=``implicit_not_observed``）；
- ``check_type=unique``（M2 新增，依 §6.1 c)「仅保留一份文件元数据隐式标识」）：
  同一国标字段被**多个不同容器键**同时提供 → ``fail``(``duplicate_implicit_label``)；
- **非生效（pending）规则不参与判定**——映射表与规则库同为门控对象。
"""

from ..mapping import resolve_fields
from ..model import (
    OBSERVED_IMPLICIT, STATUS_FAIL, STATUS_PASS, STATUS_SKIPPED, STATUS_UNKNOWN, Finding,
)
from ..rules.rule import SCOPE_IMPLICIT, evaluate

CODE_FIELD_ABSENT = "field_absent"
CODE_FIELD_ABSENT_CANNOT_VERIFY = "field_absent_cannot_verify"
CODE_SCENARIO_NOT_APPLICABLE = "scenario_not_applicable"
CODE_IMPLICIT_NOT_OBSERVED = "implicit_not_observed"
CODE_DUPLICATE_IMPLICIT_LABEL = "duplicate_implicit_label"


def _finding(rule, status, code, message, evidence=None, scenario=""):
    return Finding(
        scope=SCOPE_IMPLICIT,
        target=rule.target,
        status=status,
        code=code,
        message=message,
        clause=rule.clause,
        evidence=evidence,
        severity=rule.severity,
        scenario=scenario or (rule.scenarios[0] if rule.scenarios else ""),
    )


def check_implicit(card, ruleset, mapping_table):
    """对隐式字段逐条核验，返回 :class:`Finding` 列表（顺序 = 规则加载序）。"""
    # 全表归一：规则未覆盖到的字段也解析，便于报告与调试
    resolutions = resolve_fields(card.implicit, mapping_table)

    applicable, skipped = ruleset.rules_for_card(SCOPE_IMPLICIT, card.carrier, card.scenario)

    def finding(rule, status, code, message, evidence=None):
        return _finding(rule, status, code, message, evidence, scenario=card.scenario)

    findings = []
    for rule in skipped:
        findings.append(finding(
            rule, STATUS_SKIPPED, CODE_SCENARIO_NOT_APPLICABLE,
            "场景不适用（本条仅适用于 {0}）：{1}".format(
                "/".join(rule.scenarios), card.scenario),
            {"scenario": card.scenario, "applies_to": rule.scenarios},
        ))

    observed = card.observes(OBSERVED_IMPLICIT)
    for rule in applicable:
        if not observed:
            findings.append(finding(
                rule, STATUS_UNKNOWN, CODE_IMPLICIT_NOT_OBSERVED,
                "隐式标识作用域未被观测（无元数据来源），不臆测合规性",
                {"observed": False},
            ))
            continue

        if rule.check_type == "unique":
            findings.append(_check_unique(rule, resolutions, card, card.scenario))
            continue

        resolution = resolutions.get(rule.target)
        if resolution is None:
            # 规则引用了映射表中不存在的国标字段 → 数据缺陷（不猜、不计违规）
            findings.append(finding(
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
                findings.append(finding(
                    rule, STATUS_FAIL, CODE_FIELD_ABSENT,
                    "隐式标识字段缺失：{0}".format(rule.target), evidence,
                ))
            else:
                findings.append(finding(
                    rule, STATUS_UNKNOWN, CODE_FIELD_ABSENT_CANNOT_VERIFY,
                    "隐式字段缺失，无法核验其{0}约束：{1}".format(rule.check_type, rule.target),
                    evidence,
                ))
            continue

        status, code, message, extra = evaluate(rule, resolution.value)
        evidence.update(extra)
        findings.append(finding(rule, status, code, message, evidence))

    return findings


def _check_unique(rule, resolutions, card, scenario):
    """判定"文件元数据隐式标识是否被重复保留"（GB 45438-2025 §6.1 c)）。

    该条约束的对象是**整块隐式标识**（不是单个要素），故逐要素巡查全部归一结果，
    任一要素出现下列情形即视为重复：

    1. **同一要素被多个容器键同时提供**（国标字段名/多个别名并存 → 多份副本）；
    2. 解析通路登记了 ``card.implicit_duplicate_keys``（同一容器键出现多次；字典形态
       看不见重复，故由解析通路据实登记）。

    无任何命中 → 无法核验（``unknown``，不臆测）；全部要素各恰一份 → ``pass``；
    存在重复 → ``fail``，evidence 列出**全部重复要素及其命中键**（不静默取一）。
    """
    duplicated = []
    for national_field, resolution in resolutions.items():
        keys = resolution.all_matched_keys
        repeated = [key for key in card.implicit_duplicate_keys if key in keys]
        if len(keys) + len(repeated) > 1:
            duplicated.append({
                "national_field": national_field,
                "keys": keys,
                "repeated_keys": repeated,
            })

    observed_keys = [key for resolution in resolutions.values()
                     for key in resolution.all_matched_keys]
    evidence = {
        "observed_keys": observed_keys,
        "duplicated": duplicated,
    }

    if not observed_keys:
        return _finding(
            rule, STATUS_UNKNOWN, CODE_FIELD_ABSENT_CANNOT_VERIFY,
            "未观测到任何隐式标识要素，无法核验唯一性约束", evidence, scenario=scenario,
        )
    if not duplicated:
        return _finding(rule, STATUS_PASS, "", "文件元数据隐式标识仅保留一份", evidence,
                        scenario=scenario)
    return _finding(
        rule, STATUS_FAIL, CODE_DUPLICATE_IMPLICIT_LABEL,
        "文件元数据隐式标识被重复保留（{0} 个要素存在多份）：同一标识应仅保留一份".format(
            len(duplicated)),
        evidence,
        scenario=scenario,
    )


__all__ = [
    "check_implicit",
    "CODE_FIELD_ABSENT", "CODE_FIELD_ABSENT_CANNOT_VERIFY",
    "CODE_SCENARIO_NOT_APPLICABLE", "CODE_IMPLICIT_NOT_OBSERVED",
    "CODE_DUPLICATE_IMPLICIT_LABEL",
]
