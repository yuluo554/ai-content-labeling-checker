"""显式标识核验引擎（契约见 plan/04 §四）。

对每条 ``scope=explicit`` 且载体匹配的**生效**规则，在标识卡的 ``explicit[]``
中定位要素并判定。关键纪律：

- **不只判"有没有"，还判"位置形式对不对"**（FR-2 = ``position`` check_type）；
- 要素缺失时：``presence`` 类判 ``fail``；其余类型判 ``unknown``（**不臆测合规**）；
- ``present=true`` 但缺 ``position`` → ``unknown``（无法核验位置约束）。
"""

from ..model import STATUS_FAIL, STATUS_PASS, STATUS_UNKNOWN, Finding
from ..model import LabelCard  # noqa: F401  (类型标注可读性)
from ..rules.rule import SCOPE_EXPLICIT, evaluate

CODE_ELEMENT_ABSENT = "element_absent"
CODE_ELEMENT_NOT_PRESENT = "element_not_present"
CODE_POSITION_UNKNOWN = "position_unknown"


def _finding(rule, status, code, message, evidence=None):
    return Finding(
        scope=SCOPE_EXPLICIT,
        target=rule.target,
        status=status,
        code=code,
        message=message,
        clause=rule.clause,
        evidence=evidence,
        severity=rule.severity,
    )


def check_explicit(card, ruleset):
    """对显式要素逐条核验，返回 :class:`Finding` 列表（顺序 = 规则加载序）。"""
    findings = []
    for rule in ruleset.rules_for(SCOPE_EXPLICIT, card.carrier):
        element = card.find_explicit(rule.target)

        if element is None:
            if rule.check_type == "presence":
                findings.append(_finding(
                    rule, STATUS_FAIL, CODE_ELEMENT_ABSENT,
                    "显式标识要素缺失：{0}".format(rule.target),
                    {"observed": None},
                ))
            else:
                findings.append(_finding(
                    rule, STATUS_UNKNOWN,
                    "element_absent_cannot_verify",
                    "显式要素缺失，无法核验其{0}约束".format(rule.check_type),
                    {"observed": None},
                ))
            continue

        present = element.get("present")
        if present is False:
            findings.append(_finding(
                rule, STATUS_FAIL, CODE_ELEMENT_NOT_PRESENT,
                "显式标识要素声明为不存在：{0}".format(rule.target),
                {"observed": False},
            ))
            continue
        if present is not True:
            # present 缺失或非布尔 → 不可判定（不猜）
            findings.append(_finding(
                rule, STATUS_UNKNOWN, "element_presence_unknown",
                "显式要素未声明 present，无法判定是否具备标识：{0}".format(rule.target),
                {"observed": present},
            ))
            continue

        # present == True：按 check_type 判定（position 取 element["position"]，其余取 element["value"]）
        if rule.check_type == "presence":
            findings.append(_finding(
                rule, STATUS_PASS, "", "显式标识要素存在", {"observed": True},
            ))
        elif rule.check_type == "position":
            observed_position = element.get("position")
            if observed_position is None:
                findings.append(_finding(
                    rule, STATUS_UNKNOWN, CODE_POSITION_UNKNOWN,
                    "要素存在但未记录位置，无法核验位置约束：{0}".format(rule.target),
                    {"observed": None, "expected": rule.params.get("allowed", [])},
                ))
            else:
                status, code, message, evidence = evaluate(rule, observed_position)
                findings.append(_finding(rule, status, code, message, evidence))
        else:
            observed_value = element.get("value")
            status, code, message, evidence = evaluate(rule, observed_value)
            findings.append(_finding(rule, status, code, message, evidence))

    return findings


__all__ = ["check_explicit", "CODE_ELEMENT_ABSENT", "CODE_ELEMENT_NOT_PRESENT", "CODE_POSITION_UNKNOWN"]
