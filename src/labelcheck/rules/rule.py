"""规则条目模型与判定分派（契约见 plan/04 §三.3）。

**本模块零 I/O**：只定义规则数据结构与 check_type 分派；加载由 ``loader`` 负责。
"""

import re

from ..errors import RulesetError
from ..model import SCENARIOS, STATUS_FAIL, STATUS_PASS, STATUS_UNKNOWN, Finding

#: 支持的判定类型（契约见 plan/04 §三.3）。
#: ``unique``（M2 新增）语义特殊：它要求**整个隐式标识块**的上下文（判断同一国标字段
#: 是否被多份副本/多个别名键重复提供），故由 ``engine.implicit`` 直接判定，不经
#: :func:`evaluate`。其依据为 GB 45438-2025 §6.1 c)「应仅保留一份文件元数据隐式标识」。
CHECK_TYPES = ("presence", "position", "enum", "pattern", "type", "range", "unique")

SCOPE_EXPLICIT = "explicit"
SCOPE_IMPLICIT = "implicit"
SCOPES = (SCOPE_EXPLICIT, SCOPE_IMPLICIT)

#: 核对状态枚举——只有 verified 能进判定路径（NFR-4）
STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"
VERIFY_STATUSES = (STATUS_VERIFIED, STATUS_PENDING)


class Rule(object):
    """单条核查规则。"""

    __slots__ = ("rule_id", "scope", "carrier", "target", "check_type",
                 "params", "severity", "only_if", "clause", "status",
                 "source_url", "verified_at", "doc_id", "version")

    def __init__(self, rule_id, scope, target, check_type, carrier=None, params=None,
                 severity="major", only_if=None, clause=None, status=STATUS_PENDING,
                 source_url="", verified_at=None, doc_id="", version=""):
        self.rule_id = rule_id
        self.scope = scope
        self.target = target
        self.check_type = check_type
        self.carrier = list(carrier) if carrier else []
        self.params = dict(params) if params else {}
        self.severity = severity
        self.only_if = dict(only_if) if only_if else {}
        self.clause = dict(clause) if clause else {}
        self.status = status
        self.source_url = source_url
        self.verified_at = verified_at
        self.doc_id = doc_id
        self.version = version

    @property
    def is_effective(self):
        """该条目是否已核对通过（可进判定路径）。"""
        return self.status == STATUS_VERIFIED

    def applies_to_carrier(self, carrier):
        """载体门控：空列表 = 全部载体适用。"""
        return not self.carrier or carrier in self.carrier

    @property
    def scenarios(self):
        """``only_if.scenario`` 声明的适用场景（空 = 全部场景适用，**默认口径**）。"""
        return list(self.only_if.get("scenario") or [])

    def applies_to_scenario(self, scenario):
        """场景门控（适用性画像）：空列表 = 全部场景适用；否则须精确命中。

        不适用 → 引擎记 ``skipped``（**不是 fail**）：办法第四条第二款（导出文件）与
        第六条（传播平台提示）只对特定场景成立，把"不适用"判成"违规"是冤枉用户。
        """
        declared = self.scenarios
        return not declared or scenario in declared

    def __repr__(self):
        return "Rule({0}, scope={1}, type={2}, status={3})".format(
            self.rule_id, self.scope, self.check_type, self.status
        )


def _coerce_scalar_list(values):
    return [v for v in values if v is not None]


def evaluate(rule, observed):
    """按 ``rule.check_type`` 判定观测值，返回 ``(status, code, message, evidence)``。

    :param rule: :class:`Rule`
    :param observed: 观测值；``None`` 表示缺失；显式要素的字典形态由调用方归一。

    判定语义严格按 plan/04 §三.3；**缺值不臆测**（非 presence 类一律 unknown）。

    ``check_type="unique"`` 需要整个隐式标识块作为上下文（见 :data:`CHECK_TYPES`），
    由 ``engine.implicit`` 直接判定——这里显式拒绝，避免调用方误用。
    """
    params = rule.params
    check_type = rule.check_type

    if check_type == "unique":
        raise RulesetError(
            "check_type=unique 需整块上下文，须由 engine.implicit 判定（规则 {0}）".format(
                rule.rule_id))

    if check_type == "presence":
        if observed is None or observed == "":
            return (STATUS_FAIL, "element_absent" if rule.scope == SCOPE_EXPLICIT else "field_absent",
                    "必需项缺失", {"observed": None})
        return (STATUS_PASS, "", "存在且非空", {"observed": observed})

    # 以下类型：缺值不判定
    if observed is None:
        code = "element_absent_cannot_verify" if rule.scope == SCOPE_EXPLICIT else "field_absent_cannot_verify"
        return (STATUS_UNKNOWN, code, "缺值，无法核验该项约束", {"observed": None})

    if check_type == "position":
        allowed = params.get("allowed", [])
        value = observed
        if value in allowed:
            return (STATUS_PASS, "", "位置在允许集内", {"observed": value, "expected": allowed})
        return (STATUS_FAIL, "position_not_allowed", "位置不在允许集内",
                {"observed": value, "expected": allowed})

    if check_type == "enum":
        allowed = params.get("allowed", [])
        value = observed
        if value in allowed:
            return (STATUS_PASS, "", "取值在枚举内", {"observed": value, "expected": allowed})
        return (STATUS_FAIL, "value_not_allowed", "取值不在枚举内",
                {"observed": value, "expected": allowed})

    if check_type == "pattern":
        pattern = params.get("regex", "")
        text = observed if isinstance(observed, str) else str(observed)
        try:
            matched = re.fullmatch(pattern, text) is not None
        except re.error as exc:
            raise RulesetError(
                "规则 {0} 的 regex 非法：{1}（{2}）".format(rule.rule_id, pattern, exc)
            )
        if matched:
            return (STATUS_PASS, "", "格式匹配", {"observed": text, "expected": pattern})
        return (STATUS_FAIL, "format_mismatch", "格式不匹配",
                {"observed": text, "expected": pattern})

    if check_type == "type":
        expect = params.get("expect", "string")
        if _type_matches(observed, expect):
            return (STATUS_PASS, "", "类型匹配", {"observed": type(observed).__name__, "expected": expect})
        return (STATUS_FAIL, "type_mismatch", "类型不匹配",
                {"observed": type(observed).__name__, "expected": expect})

    if check_type == "range":
        return _evaluate_range(rule, observed)

    raise RulesetError("未知 check_type：{0!r}（规则 {1}）".format(check_type, rule.rule_id))


def _type_matches(value, expect):
    if expect == "string":
        return isinstance(value, str)
    if expect == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if expect == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expect == "bool":
        return isinstance(value, bool)
    if expect == "list":
        return isinstance(value, list)
    if expect == "object":
        return isinstance(value, dict)
    raise RulesetError("未知 type 期望：{0!r}".format(expect))


def _evaluate_range(rule, observed):
    params = rule.params
    try:
        value = float(observed)
    except (TypeError, ValueError):
        return (STATUS_FAIL, "type_mismatch", "取值范围检查要求数值", {"observed": observed})
    low = params.get("min", None)
    high = params.get("max", None)
    ok = True
    if low is not None and value < low:
        ok = False
    if high is not None and value > high:
        ok = False
    expected = {"min": low, "max": high}
    if ok:
        return (STATUS_PASS, "", "取值在范围内", {"observed": value, "expected": expected})
    return (STATUS_FAIL, "value_out_of_range", "取值超出范围",
            {"observed": value, "expected": expected})


__all__ = [
    "Rule", "evaluate", "CHECK_TYPES", "SCOPES",
    "SCOPE_EXPLICIT", "SCOPE_IMPLICIT",
    "STATUS_VERIFIED", "STATUS_PENDING", "VERIFY_STATUSES",
    "SCENARIOS",
]
