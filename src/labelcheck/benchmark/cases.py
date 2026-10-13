# -*- coding: utf-8 -*-
"""基准算例与对账口径的**单一实现源**（FR-11，契约见 plan/04 §九 / plan/05 §三.2）。

**为什么要有这个模块**：三类基准（``fields`` / ``constructed`` / ``diff``）与
真值库对账测试（``tests/test_generators.py``、``tests/test_parse_regression.py``）
若各写一套"期望 vs 实际"的比对逻辑，就会出现"基准说达标、测试说不过"的双口径。
故本模块提供：

1. :func:`observed_nonpass` / :func:`compare_nonpass` —— **对账口径的唯一实现**
   （plan/05 §三.2：比对 ``expected`` 声明的**非 pass 集合**与引擎实际非 pass 集合；
   ``fail ∪ unknown``，**未观测的 scope 排除在比较之外**）；
2. :func:`field_cases` —— 逐 ``check_type`` 的确定性边界/畸形用例（存在性/类型/格式/取值）；
3. :func:`constructed_cases` —— 程序化构造带**已知标识配置**的合成件（注入缺陷已知）；
4. :func:`diff_scenarios` —— 两轮扫描对账的确定性算例。

**纪律**：

- **不许改真值凑引擎**：``expected`` 由**注入点**定义（"我注入了 F 字段缺失，故 F 应判
  fail"），而不是把引擎输出抄成期望；
- **零政策字面量**：国标字段名、显式要素 id、位置/取值枚举**一律从规则库/映射表读取**
  （:func:`explicit_targets_for` / :func:`implicit_targets_for` / :func:`rule_of_type`），
  源码里不出现任何规则取值（NFR-5，守门测试 ``test_guard_data.py`` 扫描本模块）；
- **零时钟/零随机**：指纹由算例 id 确定性派生，件序固定 → 同一输入两次运行逐字节一致。

**判定断言的两种形态**（避免"同一 target 被多条规则判定"造成的假冲突）：

- ``expect``：**必须出现**的判定（scope × target × status × code 四元组精确匹配）；
- ``forbid``：**必须不出现**的判定（同样四元组匹配）。

同一 target 常被多条规则判定（如显式要素有 presence + position + 两条 pattern 共 4 条；
隐式"生成合成属性"要素另有 §6.1 c) 唯一性规则），故 **``forbid`` 只许禁止带具体原因码的判定**
（``fail``/``unknown`` 的某个 code），**不得**禁止裸 ``pass``
——那会命中同 target 上另一条规则的 pass（是断言写法问题，不是引擎问题）。
"""

import re

from ..engine import check_card, check_card_dict
from ..jsonio import sha256_text, write_json
from ..mapping import load_mapping_table
from ..model import (
    OBSERVED_EXPLICIT, OBSERVED_IMPLICIT, SCENARIO_AUTHORED, SCENARIO_EXPORTED,
    SCENARIO_PROPAGATED, STATUS_FAIL, STATUS_PASS, STATUS_UNKNOWN,
)
from ..rules import effective_ruleset
from ..scan import KIND_CARD, ScanItem, ScanResult, diff_scans

#: 作用域顺序（确定性：显式在前，与报告一致）
SCOPE_ORDER = (OBSERVED_EXPLICIT, OBSERVED_IMPLICIT)

#: 非 pass 状态（对账口径 = fail ∪ unknown，plan/05 §三.2）
NONPASS_STATUSES = (STATUS_FAIL, STATUS_UNKNOWN)

#: 构造用例时用的"必定越界"取值（不在任何规则 allowed 集内；非政策字面量）
OUT_OF_SET = "out-of-allowed-set"
#: 构造用例时用的中性文本（不含任何必需要素片段；非政策字面量）
NEUTRAL_TEXT = "sample-text"

#: 解析 pattern 规则里的分组（取"第一选项"拼出合规取值 → 期望值由规则库派生，不硬编码）
_GROUP_RE = re.compile(r"\(([^()]*)\)")

#: 集合名（对账结果的全部集合，顺序固定）
DIFF_COLLECTIONS = (
    "added", "fixed", "persistent", "stable", "new_items", "removed", "content_changed",
)


# ---------------------------------------------------------------- 对账口径（单一实现）
def findings_for(report, scope):
    """取某 scope 的判定列表（顺序 = 引擎产出序）。"""
    return report.explicit if scope == OBSERVED_EXPLICIT else report.implicit


def observed_nonpass(report, scope):
    """该 scope 的**非 pass 目标集**（``fail ∪ unknown``，排序去重）。

    :returns: 目标列表；该 scope **未被观测**时返回 ``None``
        （引擎对其一律判 ``unknown``，那是"没看到"而不是"缺失"——无从比较，
        故排除在比较之外；解析通路的显式作用域恒为 ``None``）。
    """
    if not report.observed.get(scope, True):
        return None
    targets = set()
    for finding in findings_for(report, scope):
        if finding.status in NONPASS_STATUSES:
            targets.add(finding.target)
    return sorted(targets)


def observed_fail(report, scope):
    """该 scope 的 ``fail`` 目标集（排序去重）；未观测 → ``None``。"""
    if not report.observed.get(scope, True):
        return None
    targets = set()
    for finding in findings_for(report, scope):
        if finding.status == STATUS_FAIL:
            targets.add(finding.target)
    return sorted(targets)


def compare_nonpass(report, expected):
    """把报告的非 pass 集合与 ``expected`` 声明的目标集比对。

    :param expected: ``{scope: [target, …]}``——声明"该 scope 非 pass 的目标"
        （``fail ∪ unknown`` 同目标算一个，与 plan/05 §三.2 一致）
    :returns: 不一致描述列表（空 = 一致）

    未观测的 scope 不参与比较（解析通路"显式恒未观测"正是这一形态）。
    """
    mismatches = []
    for scope in SCOPE_ORDER:
        declared = sorted(set(expected.get(scope, []) or []))
        actual = observed_nonpass(report, scope)
        if actual is None:
            continue
        if actual != declared:
            mismatches.append("{0} 非 pass 集合 {1} != 期望 {2}".format(scope, actual, declared))
    return mismatches


# ---------------------------------------------------------------- 规则库访问（零硬编码）
def explicit_targets_for(ruleset, carrier, scenario):
    """该载体 × 场景下适用的显式要素 target（保序去重；来自规则库）。"""
    out = []
    for rule in ruleset.effective:
        if rule.scope != OBSERVED_EXPLICIT:
            continue
        if not rule.applies_to_carrier(carrier) or not rule.applies_to_scenario(scenario):
            continue
        if rule.target not in out:
            out.append(rule.target)
    return out


def implicit_targets_for(ruleset, carrier, scenario):
    """该载体 × 场景下适用的隐式字段 target（保序去重；来自规则库）。"""
    out = []
    for rule in ruleset.effective:
        if rule.scope != OBSERVED_IMPLICIT:
            continue
        if not rule.applies_to_carrier(carrier) or not rule.applies_to_scenario(scenario):
            continue
        if rule.target not in out:
            out.append(rule.target)
    return out


def rule_of_type(ruleset, scope, target, check_type, carrier=None, scenario=None):
    """取一条具体规则（scope × target × check_type，可加载体/场景约束）；无则 ``None``。"""
    for rule in ruleset.effective:
        if rule.scope != scope or rule.target != target or rule.check_type != check_type:
            continue
        if carrier is not None and not rule.applies_to_carrier(carrier):
            continue
        if scenario is not None and not rule.applies_to_scenario(scenario):
            continue
        return rule
    return None


def pattern_fragments(ruleset, scope, target, carrier, scenario):
    """从 pattern 规则的 regex 取**必需片段**（各分组第一选项，按规则加载序）。

    合规取值 = 片段拼接；缺某片段 = 该 pattern 规则必然 fail。这样"什么算合规取值"
    由**规则库自身**决定，基准不抄一份正则（零政策字面量）。
    """
    fragments = []
    for rule in ruleset.effective:
        if rule.scope != scope or rule.target != target or rule.check_type != "pattern":
            continue
        if not rule.applies_to_carrier(carrier) or not rule.applies_to_scenario(scenario):
            continue
        groups = _GROUP_RE.findall(rule.params.get("regex", ""))
        if groups:
            fragments.append(groups[0].split("|")[0])
    return fragments


def allowed_values(ruleset, scope, target, check_type, carrier=None, scenario=None):
    """取 position/enum 规则的 ``params.allowed``（无该规则 → 空列表）。"""
    rule = rule_of_type(ruleset, scope, target, check_type, carrier, scenario)
    if rule is None:
        return []
    return list(rule.params.get("allowed", []) or [])


def severities_for(ruleset, scope, target, carrier=None, scenario=None):
    """该 target 上全部适用规则的严重度（保序去重；来自规则库）。"""
    out = []
    for rule in ruleset.effective:
        if rule.scope != scope or rule.target != target:
            continue
        if carrier is not None and not rule.applies_to_carrier(carrier):
            continue
        if scenario is not None and not rule.applies_to_scenario(scenario):
            continue
        if rule.severity not in out:
            out.append(rule.severity)
    return out


def unique_rule(ruleset):
    """取 ``check_type=unique`` 的生效规则（无则 ``None``）。"""
    for rule in ruleset.effective:
        if rule.check_type == "unique":
            return rule
    return None


def grade_for_fail_severities(severities):
    """按分级规则（plan/04 §六）由 fail 的严重度集推出期望等级。"""
    if not severities:
        return None
    if "critical" in severities or "major" in severities:
        return "non_compliant"
    return "partial"


# ---------------------------------------------------------------- 标识卡构造
def make_card(card_id, carrier, explicit=None, implicit=None, scenario=None, observed=None,
              implicit_duplicate_keys=None, source="synthetic"):
    """构造一张基准用标识卡（内容指纹由 card_id 确定性派生 → 无时钟/无随机）。"""
    card = {
        "card_id": card_id,
        "carrier": carrier,
        "source": source,
        "content_sha256": sha256_text("bench-content::{0}".format(card_id)),
        "explicit": list(explicit or []),
        "implicit": dict(implicit or {}),
        "notes": "基准算例（内容完全虚构）",
    }
    if scenario is not None:
        card["scenario"] = scenario
    if observed is not None:
        card["observed"] = dict(observed)
    if implicit_duplicate_keys is not None:
        card["implicit_duplicate_keys"] = list(implicit_duplicate_keys)
    return card


def valid_implicit_value(ruleset, field, carrier, scenario):
    """该隐式字段的**合规取值**（有 enum 规则取允许集首项，否则给非空字符串）。"""
    allowed = allowed_values(ruleset, OBSERVED_IMPLICIT, field, "enum", carrier, scenario)
    if allowed:
        return allowed[0]
    return "SYN-VALUE-0001"


def explicit_element(ruleset, target, carrier, scenario):
    """该显式要素的**合规要素对象**（位置取允许集首项、取值由 pattern 片段拼出）。"""
    element = {"element": target, "present": True}
    allowed = allowed_values(ruleset, OBSERVED_EXPLICIT, target, "position", carrier, scenario)
    if allowed:
        element["position"] = allowed[0]
    fragments = pattern_fragments(ruleset, OBSERVED_EXPLICIT, target, carrier, scenario)
    element["value"] = "".join(fragments) if fragments else "SYN-NOTICE-0001"
    return element


def full_implicit(ruleset, carrier, scenario, overrides=None):
    """该载体 × 场景下**全部隐式字段齐备**的字典（overrides 覆盖个别字段）。"""
    data = dict((field, valid_implicit_value(ruleset, field, carrier, scenario))
                for field in implicit_targets_for(ruleset, carrier, scenario))
    data.update(overrides or {})
    return data


def valid_card(ruleset, card_id, carrier, scenario=SCENARIO_AUTHORED):
    """构造该载体 × 场景下**全要素合规**的标识卡（期望值全部由规则库派生）。"""
    explicit = [
        explicit_element(ruleset, target, carrier, scenario)
        for target in explicit_targets_for(ruleset, carrier, scenario)
    ]
    implicit = full_implicit(ruleset, carrier, scenario)
    return make_card(card_id, carrier, explicit=explicit, implicit=implicit, scenario=scenario)


def field_key(mapping, field):
    """该字段可用的容器键（国标字段名自身即合法键；映射表 keys = 字段名 + 别名）。"""
    item = mapping.by_field(field)
    return item.keys if item is not None else [field]


def alias_key(mapping, field):
    """该字段的**别名**键（无别名 → ``None``）；用于构造"同一要素多份副本"。"""
    item = mapping.by_field(field)
    if item is None or not item.aliases:
        return None
    return item.aliases[0]


# ---------------------------------------------------------------- fields 基准
def _finding(scope, target, status, code):
    """一条断言（scope × target × status × code 四元组）。"""
    return {"scope": scope, "target": target, "status": status, "code": code}


def field_cases(ruleset, mapping, carrier="text", scenario=SCENARIO_AUTHORED):
    """逐 ``check_type`` 的确定性边界/畸形用例（FR-11 的 ``fields`` 基准）。

    每个用例声明**必须出现**的判定（``expect``）与**必须不出现**的判定（``forbid``），
    期望值取自规则库语义（plan/04 §三.3 的 check_type 分派表），不抄引擎输出。

    :returns: 用例 dict 列表（``card`` 为该例的输入标识卡）
    """
    cases = []
    elements = explicit_targets_for(ruleset, carrier, scenario)
    fields = implicit_targets_for(ruleset, carrier, scenario)
    if not elements or not fields:
        return cases

    element = elements[0]
    uniq = unique_rule(ruleset)
    unique_target = uniq.target if uniq is not None else None
    # 主字段避开 unique 规则的目标（避免"同一 target 多条规则"的断言撞车）
    plain_fields = [f for f in fields if f != unique_target]
    field = plain_fields[0] if plain_fields else fields[0]
    key = field_key(mapping, field)[0]
    alias = alias_key(mapping, field)

    def card(card_id, explicit=None, implicit=None, **kwargs):
        return make_card(card_id, carrier, explicit=explicit, implicit=implicit,
                         scenario=scenario, **kwargs)

    def implicit_with(overrides):
        return full_implicit(ruleset, carrier, scenario, overrides)

    def drop_field(name):
        data = full_implicit(ruleset, carrier, scenario)
        data.pop(name, None)
        return data

    # ---- 存在性（显式要素） ------------------------------------------------
    cases.append({
        "case_id": "FIELD-PRESENCE-ELEMENT-OK",
        "check_type": "presence",
        "description": "显式要素齐备且取值/位置合规 → pass",
        "card": card("FIELD-PRESENCE-ELEMENT-OK",
                     explicit=[explicit_element(ruleset, element, carrier, scenario)],
                     implicit=implicit_with({})),
        "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_PASS, "")],
        "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "element_absent")],
    })
    cases.append({
        "case_id": "FIELD-PRESENCE-ELEMENT-ABSENT",
        "check_type": "presence",
        "description": "显式要素整体缺失 → presence 判 fail；位置/格式类因缺值判 unknown（不臆测）",
        "card": card("FIELD-PRESENCE-ELEMENT-ABSENT", explicit=[], implicit=implicit_with({})),
        "expect": [
            _finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "element_absent"),
            _finding(OBSERVED_EXPLICIT, element, STATUS_UNKNOWN,
                     "element_absent_cannot_verify"),
        ],
        "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "element_not_present")],
        "expect_grade": "non_compliant",
    })
    cases.append({
        "case_id": "FIELD-PRESENCE-ELEMENT-FALSE",
        "check_type": "presence",
        "description": "要素声明 present=false → fail（element_not_present）",
        "card": card("FIELD-PRESENCE-ELEMENT-FALSE",
                     explicit=[{"element": element, "present": False}],
                     implicit=implicit_with({})),
        "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "element_not_present")],
        "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "element_absent")],
    })
    cases.append({
        "case_id": "FIELD-PRESENCE-ELEMENT-UNKNOWN-PRESENCE",
        "check_type": "presence",
        "description": "畸形输入：present 非布尔 → unknown（element_presence_unknown，不猜）",
        "card": card("FIELD-PRESENCE-ELEMENT-UNKNOWN-PRESENCE",
                     explicit=[{"element": element, "present": "yes"}],
                     implicit=implicit_with({})),
        "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_UNKNOWN,
                            "element_presence_unknown")],
        "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "element_absent")],
    })

    # ---- 位置（position） -------------------------------------------------
    positions = allowed_values(ruleset, OBSERVED_EXPLICIT, element, "position", carrier, scenario)
    if positions:
        good = explicit_element(ruleset, element, carrier, scenario)
        good["position"] = positions[0]
        cases.append({
            "case_id": "FIELD-POSITION-ALLOWED",
            "check_type": "position",
            "description": "位置落在允许集内 → pass",
            "card": card("FIELD-POSITION-ALLOWED", explicit=[good], implicit=implicit_with({})),
            "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_PASS, "")],
            "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "position_not_allowed")],
        })
        bad = explicit_element(ruleset, element, carrier, scenario)
        bad["position"] = OUT_OF_SET
        cases.append({
            "case_id": "FIELD-POSITION-NOT-ALLOWED",
            "check_type": "position",
            "description": "位置越界 → fail（position_not_allowed）",
            "card": card("FIELD-POSITION-NOT-ALLOWED", explicit=[bad], implicit=implicit_with({})),
            "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "position_not_allowed")],
            "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_UNKNOWN, "position_unknown")],
        })
        nopos = explicit_element(ruleset, element, carrier, scenario)
        nopos.pop("position", None)
        cases.append({
            "case_id": "FIELD-POSITION-MISSING",
            "check_type": "position",
            "description": "要素在但未记录位置 → unknown（position_unknown，不臆测）",
            "card": card("FIELD-POSITION-MISSING", explicit=[nopos], implicit=implicit_with({})),
            "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_UNKNOWN, "position_unknown")],
            "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "position_not_allowed")],
        })

    # ---- 格式（pattern） --------------------------------------------------
    fragments = pattern_fragments(ruleset, OBSERVED_EXPLICIT, element, carrier, scenario)
    if len(fragments) >= 2:
        ok = explicit_element(ruleset, element, carrier, scenario)
        ok["value"] = "".join(fragments)
        cases.append({
            "case_id": "FIELD-PATTERN-OK",
            "check_type": "pattern",
            "description": "取值含全部必需要素片段 → pass",
            "card": card("FIELD-PATTERN-OK", explicit=[ok], implicit=implicit_with({})),
            "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_PASS, "")],
            "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "format_mismatch")],
        })
        for index in range(len(fragments)):
            partial = explicit_element(ruleset, element, carrier, scenario)
            partial["value"] = "".join(
                fragment for position, fragment in enumerate(fragments) if position != index)
            cases.append({
                "case_id": "FIELD-PATTERN-MISSING-FRAGMENT-{0}".format(index + 1),
                "check_type": "pattern",
                "description": "取值缺第 {0} 个必需要素片段 → fail（format_mismatch）".format(index + 1),
                "card": card("FIELD-PATTERN-MISSING-FRAGMENT-{0}".format(index + 1),
                             explicit=[partial], implicit=implicit_with({})),
                "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "format_mismatch")],
                "forbid": [],
            })
        neutral = explicit_element(ruleset, element, carrier, scenario)
        neutral["value"] = NEUTRAL_TEXT
        cases.append({
            "case_id": "FIELD-PATTERN-NEUTRAL",
            "check_type": "pattern",
            "description": "取值不含任何必需要素片段 → fail（format_mismatch）",
            "card": card("FIELD-PATTERN-NEUTRAL", explicit=[neutral], implicit=implicit_with({})),
            "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "format_mismatch")],
            "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_UNKNOWN,
                                "element_absent_cannot_verify")],
        })
        no_value = explicit_element(ruleset, element, carrier, scenario)
        no_value.pop("value", None)
        cases.append({
            "case_id": "FIELD-PATTERN-NO-VALUE",
            "check_type": "pattern",
            "description": "畸形输入：要素无 value → unknown（element_absent_cannot_verify）",
            "card": card("FIELD-PATTERN-NO-VALUE", explicit=[no_value], implicit=implicit_with({})),
            "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_UNKNOWN,
                                "element_absent_cannot_verify")],
            "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "format_mismatch")],
        })
        non_string = explicit_element(ruleset, element, carrier, scenario)
        non_string["value"] = 12345
        cases.append({
            "case_id": "FIELD-PATTERN-NON-STRING",
            "check_type": "pattern",
            "description": "畸形输入：取值非字符串 → fail（format_mismatch）",
            "card": card("FIELD-PATTERN-NON-STRING", explicit=[non_string],
                         implicit=implicit_with({})),
            "expect": [_finding(OBSERVED_EXPLICIT, element, STATUS_FAIL, "format_mismatch")],
            "forbid": [_finding(OBSERVED_EXPLICIT, element, STATUS_UNKNOWN,
                                "element_absent_cannot_verify")],
        })

    # ---- 存在性（隐式字段，避开 unique 目标） ------------------------------
    cases.append({
        "case_id": "FIELD-PRESENCE-FIELD-OK",
        "check_type": "presence",
        "description": "隐式字段存在且非空 → pass",
        "card": card("FIELD-PRESENCE-FIELD-OK", implicit=implicit_with({})),
        "expect": [_finding(OBSERVED_IMPLICIT, field, STATUS_PASS, "")],
        "forbid": [_finding(OBSERVED_IMPLICIT, field, STATUS_FAIL, "field_absent")],
    })
    cases.append({
        "case_id": "FIELD-PRESENCE-FIELD-ABSENT",
        "check_type": "presence",
        "description": "隐式字段缺失 → presence 判 fail（field_absent）",
        "card": card("FIELD-PRESENCE-FIELD-ABSENT", implicit=drop_field(field)),
        "expect": [_finding(OBSERVED_IMPLICIT, field, STATUS_FAIL, "field_absent")],
        "forbid": [],
        "expect_grade": grade_for_fail_severities(
            severities_for(ruleset, OBSERVED_IMPLICIT, field, carrier, scenario)),
    })
    cases.append({
        "case_id": "FIELD-PRESENCE-FIELD-EMPTY",
        "check_type": "presence",
        "description": "边界输入：字段存在但为空串 → 与缺失同判 fail（field_absent）",
        "card": card("FIELD-PRESENCE-FIELD-EMPTY", implicit=implicit_with({field: ""})),
        "expect": [_finding(OBSERVED_IMPLICIT, field, STATUS_FAIL, "field_absent")],
        "forbid": [],
    })

    # ---- 取值（enum） -----------------------------------------------------
    enum_field = None
    for candidate in fields:
        if allowed_values(ruleset, OBSERVED_IMPLICIT, candidate, "enum", carrier, scenario):
            enum_field = candidate
            break
    if enum_field is not None:
        allowed_enum = allowed_values(
            ruleset, OBSERVED_IMPLICIT, enum_field, "enum", carrier, scenario)
        cases.append({
            "case_id": "FIELD-ENUM-ALLOWED",
            "check_type": "enum",
            "description": "取值在枚举内 → pass",
            "card": card("FIELD-ENUM-ALLOWED",
                         implicit=implicit_with({enum_field: allowed_enum[0]})),
            "expect": [_finding(OBSERVED_IMPLICIT, enum_field, STATUS_PASS, "")],
            "forbid": [_finding(OBSERVED_IMPLICIT, enum_field, STATUS_FAIL, "value_not_allowed")],
        })
        cases.append({
            "case_id": "FIELD-ENUM-NOT-ALLOWED",
            "check_type": "enum",
            "description": "取值越界 → fail（value_not_allowed）",
            "card": card("FIELD-ENUM-NOT-ALLOWED",
                         implicit=implicit_with({enum_field: OUT_OF_SET})),
            "expect": [_finding(OBSERVED_IMPLICIT, enum_field, STATUS_FAIL, "value_not_allowed")],
            "forbid": [],
        })
        cases.append({
            "case_id": "FIELD-ENUM-EMPTY",
            "check_type": "enum",
            "description": "边界输入：取值为空串 → fail（value_not_allowed）",
            "card": card("FIELD-ENUM-EMPTY", implicit=implicit_with({enum_field: ""})),
            "expect": [_finding(OBSERVED_IMPLICIT, enum_field, STATUS_FAIL, "value_not_allowed")],
            "forbid": [],
        })
        cases.append({
            "case_id": "FIELD-ENUM-NO-VALUE",
            "check_type": "enum",
            "description": "字段缺失 → enum 因缺值判 unknown（field_absent_cannot_verify）",
            "card": card("FIELD-ENUM-NO-VALUE", implicit=drop_field(enum_field)),
            "expect": [_finding(OBSERVED_IMPLICIT, enum_field, STATUS_UNKNOWN,
                                "field_absent_cannot_verify")],
            "forbid": [_finding(OBSERVED_IMPLICIT, enum_field, STATUS_FAIL, "value_not_allowed")],
        })

    # ---- 类型（type） -----------------------------------------------------
    typed_field = None
    for candidate in fields:
        if rule_of_type(ruleset, OBSERVED_IMPLICIT, candidate, "type",
                        carrier, scenario) is not None:
            typed_field = candidate
            break
    if typed_field is not None:
        cases.append({
            "case_id": "FIELD-TYPE-STRING-OK",
            "check_type": "type",
            "description": "取值类型匹配（字符串）→ pass",
            "card": card("FIELD-TYPE-STRING-OK",
                         implicit=implicit_with({typed_field: "SYN-VALUE-0001"})),
            "expect": [_finding(OBSERVED_IMPLICIT, typed_field, STATUS_PASS, "")],
            "forbid": [_finding(OBSERVED_IMPLICIT, typed_field, STATUS_FAIL, "type_mismatch")],
        })
        cases.append({
            "case_id": "FIELD-TYPE-MISMATCH-INT",
            "check_type": "type",
            "description": "畸形输入：取值写成整数 → fail（type_mismatch）",
            "card": card("FIELD-TYPE-MISMATCH-INT",
                         implicit=implicit_with({typed_field: 12345})),
            "expect": [_finding(OBSERVED_IMPLICIT, typed_field, STATUS_FAIL, "type_mismatch")],
            "forbid": [_finding(OBSERVED_IMPLICIT, typed_field, STATUS_UNKNOWN,
                                "field_absent_cannot_verify")],
        })
        cases.append({
            "case_id": "FIELD-TYPE-MISMATCH-LIST",
            "check_type": "type",
            "description": "畸形输入：取值写成数组 → fail（type_mismatch）",
            "card": card("FIELD-TYPE-MISMATCH-LIST",
                         implicit=implicit_with({typed_field: ["a", "b"]})),
            "expect": [_finding(OBSERVED_IMPLICIT, typed_field, STATUS_FAIL, "type_mismatch")],
            "forbid": [_finding(OBSERVED_IMPLICIT, typed_field, STATUS_UNKNOWN,
                                "field_absent_cannot_verify")],
        })
        cases.append({
            "case_id": "FIELD-TYPE-NO-VALUE",
            "check_type": "type",
            "description": "字段缺失 → type 因缺值判 unknown（field_absent_cannot_verify）",
            "card": card("FIELD-TYPE-NO-VALUE", implicit=drop_field(typed_field)),
            "expect": [_finding(OBSERVED_IMPLICIT, typed_field, STATUS_UNKNOWN,
                                "field_absent_cannot_verify")],
            "forbid": [_finding(OBSERVED_IMPLICIT, typed_field, STATUS_FAIL, "type_mismatch")],
        })

    # ---- 唯一性（unique） -------------------------------------------------
    if unique_target is not None:
        unique_key = field_key(mapping, unique_target)[0]
        unique_alias = alias_key(mapping, unique_target)
        cases.append({
            "case_id": "FIELD-UNIQUE-SINGLE",
            "check_type": "unique",
            "description": "各隐式要素各恰一份 → pass",
            "card": card("FIELD-UNIQUE-SINGLE", implicit=implicit_with({})),
            "expect": [_finding(OBSERVED_IMPLICIT, unique_target, STATUS_PASS, "")],
            "forbid": [_finding(OBSERVED_IMPLICIT, unique_target, STATUS_FAIL,
                                "duplicate_implicit_label")],
        })
        if unique_alias is not None:
            duplicated = implicit_with({})
            duplicated[unique_alias] = duplicated.get(unique_key, "")
            cases.append({
                "case_id": "FIELD-UNIQUE-ALIAS-DUPLICATE",
                "check_type": "unique",
                "description": "同一要素经国标字段名与别名同时提供 → fail（duplicate_implicit_label）",
                "card": card("FIELD-UNIQUE-ALIAS-DUPLICATE", implicit=duplicated),
                "expect": [_finding(OBSERVED_IMPLICIT, unique_target, STATUS_FAIL,
                                    "duplicate_implicit_label")],
                "forbid": [],
            })
        cases.append({
            "case_id": "FIELD-UNIQUE-DECLARED-DUPLICATE",
            "check_type": "unique",
            "description": "同一容器键出现多次（解析通路据实登记）→ fail（duplicate_implicit_label）",
            "card": card("FIELD-UNIQUE-DECLARED-DUPLICATE", implicit=implicit_with({}),
                         implicit_duplicate_keys=[unique_key]),
            "expect": [_finding(OBSERVED_IMPLICIT, unique_target, STATUS_FAIL,
                                "duplicate_implicit_label")],
            "forbid": [],
        })
        cases.append({
            "case_id": "FIELD-UNIQUE-NONE",
            "check_type": "unique",
            "description": "整块隐式标识为空 → 无法核验唯一性 → unknown（不臆测）",
            "card": card("FIELD-UNIQUE-NONE", implicit={}),
            "expect": [_finding(OBSERVED_IMPLICIT, unique_target, STATUS_UNKNOWN,
                                "field_absent_cannot_verify")],
            "forbid": [_finding(OBSERVED_IMPLICIT, unique_target, STATUS_FAIL,
                                "duplicate_implicit_label")],
        })

    # ---- 场景门控（适用性画像）-------------------------------------------
    exported_targets = [
        target for target in explicit_targets_for(ruleset, carrier, SCENARIO_EXPORTED)
        if target not in explicit_targets_for(ruleset, carrier, SCENARIO_AUTHORED)
    ]
    if exported_targets:
        exported = explicit_targets_for(ruleset, carrier, SCENARIO_EXPORTED)
        cases.append({
            "case_id": "FIELD-SCENARIO-SKIPPED-IN-AUTHORED",
            "check_type": "scenario",
            "description": "导出场景独有义务在产出场景下 → skipped（不适用≠违规）",
            "card": card("FIELD-SCENARIO-SKIPPED-IN-AUTHORED",
                         explicit=[explicit_element(ruleset, target, carrier, SCENARIO_EXPORTED)
                                   for target in exported],
                         implicit=implicit_with({})),
            "expect": [_finding(OBSERVED_EXPLICIT, exported_targets[0], "skipped",
                                "scenario_not_applicable")],
            "forbid": [_finding(OBSERVED_EXPLICIT, exported_targets[0], STATUS_FAIL, "")],
        })
        cases.append({
            "case_id": "FIELD-SCENARIO-REQUIRED-IN-EXPORTED",
            "check_type": "scenario",
            "description": "导出场景下缺该场景独有义务 → fail（场景门控被正确施加）",
            "card": make_card(
                "FIELD-SCENARIO-REQUIRED-IN-EXPORTED", carrier,
                explicit=[explicit_element(ruleset, target, carrier, SCENARIO_AUTHORED)
                          for target in explicit_targets_for(ruleset, carrier, SCENARIO_AUTHORED)],
                implicit=full_implicit(ruleset, carrier, SCENARIO_EXPORTED),
                scenario=SCENARIO_EXPORTED),
            "expect": [_finding(OBSERVED_EXPLICIT, exported_targets[0], STATUS_FAIL,
                                "element_absent")],
            "forbid": [],
        })

    return cases


def missing_check_types(ruleset):
    """当前生效规则库里**没有**出现的 check_type（用例无法覆盖的类型，须显式记入说明）。

    例如 ``range`` 在建条决策中被显式判定为"不建"（plan/06 D27）——基准据此如实报告
    "该类型无规则可测"，而不是假装覆盖了。
    """
    from ..rules.rule import CHECK_TYPES

    present = set(rule.check_type for rule in ruleset.effective)
    return [name for name in CHECK_TYPES if name not in present]


# ---------------------------------------------------------------- constructed 基准
def truth_library_cases(data_dir):
    """把 ``data/truth/`` 的随附算例转成 ``constructed`` 用例（**复用既有真值**）。

    HANDOFF-M4 §三.3 要求基准**直接消费**既有真值库（8 例标识卡），**不另造一套**。
    期望值取真值库 ``expected`` 声明的非 pass 目标集（``also_expect``，即该 scope 的
    ``fail ∪ unknown`` 目标）；``injected.defect == "correct"`` 的例进误报率分母。

    :returns: 用例 dict 列表（``card`` = 真值库的 ``input_card``）；文件缺失时返回 ``[]``
    """
    from pathlib import Path

    from ..jsonio import load_json

    index_path = Path(data_dir) / "truth" / "index.json"
    if not index_path.is_file():
        return []

    index = load_json(index_path)
    cases = []
    for entry in index.get("cases", []):
        case_path = Path(data_dir) / "truth" / entry["file"]
        if not case_path.is_file():
            continue
        payload = load_json(case_path)
        expected = payload["expected"]
        also = expected.get("also_expect", {})
        expect_nonpass = {
            OBSERVED_IMPLICIT: sorted(set(also.get("implicit_fail_targets", []) or [])),
            OBSERVED_EXPLICIT: sorted(set(also.get("explicit_fail_targets", []) or [])),
        }
        defect = (expected.get("injected") or {}).get("defect", "")
        clean = defect == "correct"
        cases.append({
            "case_id": entry["case_id"],
            "group": "truth_library",
            "description": "随附真值库算例（{0}）：{1}".format(
                defect, (payload["input_card"].get("notes") or "").strip() or "（无备注）"),
            "card": payload["input_card"],
            "expect_fail": dict(expect_nonpass),
            "expect_nonpass": dict(expect_nonpass),
            "expect_grade": expected["grade"],
            # 注入型缺陷件进检出率分母；correct 件进误报率分母（口径与程序化构造例一致）
            "detection": not clean,
            "clean": clean,
            "data_dir": None,
        })
    return cases


def constructed_cases(ruleset, mapping, synthetic_dirs=None, data_dir=None):
    """程序化构造带**已知标识配置**的合成件（FR-11 的 ``constructed`` 基准）。

    每例声明：注入了什么（``group``/``description``）、期望的 ``fail`` 目标集、
    期望的非 pass 目标集（由注入点推出，非抄引擎输出）、期望等级。
    ``detection=True`` 的例进检出率分母（有注入 → 必须检出）；
    ``clean=True`` 的例进误报率分母（无注入 → 不得报出 fail）。

    :param synthetic_dirs: ``{name: path}``——引擎分支类用例所需的合成数据目录
        （由 :func:`build_synthetic_data_dirs` 产出；``None`` 时跳过该类用例并记入说明）
    :param data_dir: 数据目录；给出时会**并入** ``data/truth/`` 的随附算例
        （HANDOFF-M4 §三.3：复用既有真值，不另造一套）
    """
    cases = []
    carriers = ["text", "image", "audio", "video"]

    def add(case_id, group, description, card, expect_fail=None, expect_nonpass=None,
            expect_grade=None, detection=False, clean=False, data_dir=None):
        empty = {OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: []}
        resolved_fail = expect_fail if expect_fail is not None else empty
        cases.append({
            "case_id": case_id,
            "group": group,
            "description": description,
            "card": card,
            "expect_fail": resolved_fail,
            "expect_nonpass": expect_nonpass if expect_nonpass is not None else resolved_fail,
            "expect_grade": expect_grade,
            "detection": detection,
            "clean": clean,
            "data_dir": data_dir,
        })

    # ---- 随附真值库（复用既有算例，不另造一套）-----------------------------
    if data_dir is not None:
        cases.extend(truth_library_cases(data_dir))

    # ---- 全要素合规（每载体一例）→ 不得有任何误报 --------------------------
    for carrier in carriers:
        card = valid_card(ruleset, "CONS-CORRECT-{0}".format(carrier.upper()), carrier)
        add("CONS-CORRECT-{0}".format(carrier.upper()), "correct",
            "载体 {0} 显式 + 隐式全要素合规 → 不得有 fail（误报率分母）".format(carrier),
            card, expect_grade="compliant", clean=True)

    # ---- 场景合规（导出 / 传播）------------------------------------------
    for scenario in (SCENARIO_EXPORTED, SCENARIO_PROPAGATED):
        card = valid_card(ruleset, "CONS-CORRECT-{0}".format(scenario.upper()), "text", scenario)
        add("CONS-CORRECT-{0}".format(scenario.upper()), "correct",
            "场景 {0} 下该场景独有义务齐备 → 不得有 fail".format(scenario),
            card, expect_grade="compliant", clean=True)

    # ---- 未观测：不给假结论（不得产生 fail）-------------------------------
    unobserved_implicit = valid_card(ruleset, "CONS-UNOBSERVED-IMPLICIT", "text")
    unobserved_implicit["implicit"] = {}
    unobserved_implicit["observed"] = {OBSERVED_EXPLICIT: True, OBSERVED_IMPLICIT: False}
    add("CONS-UNOBSERVED-IMPLICIT", "unobserved",
        "隐式作用域未被观测 → 一律 unknown，不得判 fail（不得把'没看到'当'缺失'）",
        unobserved_implicit, expect_grade="partial", clean=True)

    unobserved_explicit = valid_card(ruleset, "CONS-UNOBSERVED-EXPLICIT", "text")
    unobserved_explicit["explicit"] = []
    unobserved_explicit["observed"] = {OBSERVED_EXPLICIT: False, OBSERVED_IMPLICIT: True}
    add("CONS-UNOBSERVED-EXPLICIT", "unobserved",
        "显式作用域未被观测（解析通路常态）→ 一律 unknown，不得判 fail",
        unobserved_explicit, expect_grade="partial", clean=True)

    # ---- 缺陷注入（逐类）--------------------------------------------------
    fields = implicit_targets_for(ruleset, "text", SCENARIO_AUTHORED)
    elements = explicit_targets_for(ruleset, "text", SCENARIO_AUTHORED)

    for index, name in enumerate(fields, start=1):
        card = valid_card(ruleset, "CONS-MISSING-{0:02d}".format(index), "text")
        card["implicit"].pop(name, None)
        add("CONS-MISSING-{0:02d}".format(index), "missing_field",
            "注入：隐式字段 {0} 缺失 → 该字段 fail".format(name),
            card, expect_fail={OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: [name]},
            expect_grade=grade_for_fail_severities(
                severities_for(ruleset, OBSERVED_IMPLICIT, name, "text", SCENARIO_AUTHORED)),
            detection=True)

    wrong_value_fields = [f for f in fields
                          if allowed_values(ruleset, OBSERVED_IMPLICIT, f, "enum",
                                            "text", SCENARIO_AUTHORED)]
    for index, name in enumerate(wrong_value_fields, start=1):
        card = valid_card(ruleset, "CONS-WRONGVALUE-{0:02d}".format(index), "text")
        card["implicit"][name] = OUT_OF_SET
        add("CONS-WRONGVALUE-{0:02d}".format(index), "wrong_value",
            "注入：隐式字段 {0} 取值越界 → 该字段 fail".format(name),
            card, expect_fail={OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: [name]},
            expect_grade="partial", detection=True)

    typed_fields = [f for f in fields
                    if rule_of_type(ruleset, OBSERVED_IMPLICIT, f, "type",
                                    "text", SCENARIO_AUTHORED) is not None]
    for index, name in enumerate(typed_fields, start=1):
        card = valid_card(ruleset, "CONS-BADFORMAT-{0:02d}".format(index), "text")
        card["implicit"][name] = 12345
        add("CONS-BADFORMAT-{0:02d}".format(index), "bad_format",
            "注入：隐式字段 {0} 类型不符（整数）→ 该字段 fail".format(name),
            card, expect_fail={OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: [name]},
            expect_grade="partial", detection=True)

    for carrier in carriers:
        targets = explicit_targets_for(ruleset, carrier, SCENARIO_AUTHORED)
        if not targets or not allowed_values(ruleset, OBSERVED_EXPLICIT, targets[0],
                                             "position", carrier, SCENARIO_AUTHORED):
            continue
        card = valid_card(ruleset, "CONS-WRONGPOS-{0}".format(carrier.upper()), carrier)
        card["explicit"][0]["position"] = OUT_OF_SET
        add("CONS-WRONGPOS-{0}".format(carrier.upper()), "wrong_position",
            "注入：载体 {0} 显式要素位置越界 → 该要素 fail".format(carrier),
            card, expect_fail={OBSERVED_EXPLICIT: [targets[0]], OBSERVED_IMPLICIT: []},
            expect_grade="partial", detection=True)

    stripped = valid_card(ruleset, "CONS-METADATA-STRIPPED", "image")
    stripped["implicit"] = {}
    add("CONS-METADATA-STRIPPED", "metadata_stripped",
        "边界情形：元数据整体剥离但显式齐备 → 隐式字段全 fail",
        stripped,
        expect_fail={OBSERVED_EXPLICIT: [],
                     OBSERVED_IMPLICIT: implicit_targets_for(
                         ruleset, "image", SCENARIO_AUTHORED)},
        expect_grade="non_compliant", detection=True)

    if elements:
        absent = valid_card(ruleset, "CONS-EXPLICIT-ABSENT", "text")
        absent["explicit"] = []
        add("CONS-EXPLICIT-ABSENT", "explicit_absent",
            "注入：显式要素整体缺失 → 该要素 fail",
            absent, expect_fail={OBSERVED_EXPLICIT: [elements[0]], OBSERVED_IMPLICIT: []},
            expect_grade="non_compliant", detection=True)

        not_present = valid_card(ruleset, "CONS-EXPLICIT-NOT-PRESENT", "text")
        not_present["explicit"] = [{"element": elements[0], "present": False}]
        add("CONS-EXPLICIT-NOT-PRESENT", "explicit_not_present",
            "注入：显式要素声明不存在 → 该要素 fail",
            not_present, expect_fail={OBSERVED_EXPLICIT: [elements[0]], OBSERVED_IMPLICIT: []},
            expect_grade="non_compliant", detection=True)

    uniq = unique_rule(ruleset)
    if uniq is not None and uniq.target in fields:
        alias = alias_key(mapping, uniq.target)
        if alias is not None:
            duplicate = valid_card(ruleset, "CONS-DUPLICATE-LABEL", "text")
            key = field_key(mapping, uniq.target)[0]
            duplicate["implicit"][alias] = duplicate["implicit"].get(key, "")
            add("CONS-DUPLICATE-LABEL", "duplicate_implicit",
                "注入：同一隐式要素经两个容器键提供 → 唯一性 fail",
                duplicate,
                expect_fail={OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: [uniq.target]},
                expect_grade="non_compliant", detection=True)

    minor_fields = [f for f in fields
                    if severities_for(ruleset, OBSERVED_IMPLICIT, f, "text",
                                      SCENARIO_AUTHORED) == ["minor"]]
    if minor_fields:
        only = valid_card(ruleset, "CONS-EXPLICIT-ONLY", "text")
        only["implicit"].pop(minor_fields[0], None)
        add("CONS-EXPLICIT-ONLY", "explicit_only",
            "注入：显式齐全、隐式仅缺一项 minor 要素 → partial",
            only, expect_fail={OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: [minor_fields[0]]},
            expect_grade="partial", detection=True)

    authored_targets = explicit_targets_for(ruleset, "text", SCENARIO_AUTHORED)
    propagated_only = [target for target in explicit_targets_for(ruleset, "text",
                                                                SCENARIO_PROPAGATED)
                       if target not in authored_targets]
    if propagated_only:
        propagated = valid_card(ruleset, "CONS-PROPAGATED-NO-HINT", "text", SCENARIO_PROPAGATED)
        propagated["explicit"] = [item for item in propagated["explicit"]
                                  if item["element"] in authored_targets]
        add("CONS-PROPAGATED-NO-HINT", "wrong_scenario_obligation",
            "注入：传播场景缺该场景独有提示 → 该要素 fail（场景义务被施加）",
            propagated,
            expect_fail={OBSERVED_EXPLICIT: propagated_only, OBSERVED_IMPLICIT: []},
            expect_grade="non_compliant", detection=True)

    # ---- 引擎分支（需合成数据目录）----------------------------------------
    if synthetic_dirs:
        unmapped_dir = synthetic_dirs.get("unmapped")
        if unmapped_dir is not None:
            unmapped = synthetic_unmapped_target()
            card = make_card("CONS-UNMAPPED-FIELD", "text",
                             implicit={synthetic_mapped_field(): "x"})
            add("CONS-UNMAPPED-FIELD", "engine_branch",
                "规则引用的字段不在映射表中（数据缺陷）→ unknown，不得判 fail",
                card, expect_fail={OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: []},
                expect_nonpass={OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: [unmapped]},
                expect_grade="partial", clean=True, data_dir=unmapped_dir)

        no_applicable_dir = synthetic_dirs.get("no_applicable")
        if no_applicable_dir is not None:
            card = make_card("CONS-NO-APPLICABLE-RULES", "text",
                             implicit={synthetic_mapped_field(): "x"})
            add("CONS-NO-APPLICABLE-RULES", "engine_branch",
                "当前载体下无一条规则适用 → not_assessed（'没检查'≠'合规'）",
                card, expect_fail={OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: []},
                expect_nonpass={OBSERVED_EXPLICIT: [], OBSERVED_IMPLICIT: []},
                expect_grade="not_assessed", clean=True, data_dir=no_applicable_dir)

    return cases


#: 合成数据目录里的字段名（非政策字面量：标准里不存在这些字段）
_SYNTH_FIELD = "synthetic_field_present"
_SYNTH_UNMAPPED = "synthetic_field_unmapped"
_SYNTH_DOC_ID = "synthetic-doc"
_SYNTH_VERSION = "2025-09-01"
_SYNTH_URL = "https://example.invalid/synthetic"


def synthetic_mapped_field():
    """合成数据目录中**在映射表内**的字段名。"""
    return _SYNTH_FIELD


def synthetic_unmapped_target():
    """合成数据目录中规则引用、但**不在映射表内**的字段名（数据缺陷用例）。"""
    return _SYNTH_UNMAPPED


def _synthetic_rule(rule_id, target, carrier=None):
    return {
        "rule_id": rule_id,
        "scope": OBSERVED_IMPLICIT,
        "carrier": list(carrier or []),
        "target": target,
        "check_type": "presence",
        "params": {},
        "severity": "major",
        "only_if": {},
        "clause": {"article": "合成", "excerpt": "基准自造"},
        "status": "verified",
        "source_url": _SYNTH_URL,
        "verified_at": None,
    }


def _write_synthetic_data_dir(root, rules):
    """写出一个最小数据目录（registry + 规则文件 + 映射表）。"""
    from pathlib import Path

    root = Path(root)
    write_json(root / "rules" / "registry.json", {
        "schema_version": 1,
        "documents": [{
            "doc_id": _SYNTH_DOC_ID,
            "title": "合成数据目录（基准引擎分支用例）",
            "doc_number": "SYN-DOC",
            "kind": "measure",
            "issuer": "基准自造",
            "effective_from": _SYNTH_VERSION,
            "status": "verified",
            "source_url": _SYNTH_URL,
            "versions": [{
                "version": _SYNTH_VERSION,
                "effective_from": _SYNTH_VERSION,
                "rules_file": "{0}/{1}.json".format(_SYNTH_DOC_ID, _SYNTH_VERSION),
                "status": "verified",
                "source_url": _SYNTH_URL,
                "sha256": None,
            }],
        }],
        "active": {_SYNTH_DOC_ID: _SYNTH_VERSION},
    })
    write_json(root / "rules" / _SYNTH_DOC_ID / "{0}.json".format(_SYNTH_VERSION), {
        "schema_version": 1,
        "doc_id": _SYNTH_DOC_ID,
        "version": _SYNTH_VERSION,
        "rules": rules,
    })
    write_json(root / "mapping" / "national-fields.json", {
        "schema_version": 1,
        "fields": [{
            "national_field": _SYNTH_FIELD,
            "label": _SYNTH_FIELD,
            "aliases": [],
            "status": "verified",
            "source_url": _SYNTH_URL,
            "clause": {"article": "合成", "excerpt": "基准自造"},
        }],
    })
    return root


def build_synthetic_data_dirs(root):
    """构造引擎分支用例所需的两个合成数据目录。

    :returns: ``{"unmapped": path, "no_applicable": path}``
        - ``unmapped``：规则引用的字段**不在映射表**中 → 引擎须判 unknown（数据缺陷不报违规）；
        - ``no_applicable``：唯一规则只适用另一载体 → 当前件无规则可施加 → ``not_assessed``。
    """
    from pathlib import Path

    root = Path(root)
    unmapped = _write_synthetic_data_dir(
        root / "unmapped", [_synthetic_rule("synth:unmapped", _SYNTH_UNMAPPED)])
    no_applicable = _write_synthetic_data_dir(
        root / "no-applicable",
        [_synthetic_rule("synth:other-carrier", _SYNTH_FIELD, carrier=["video"])])
    return {"unmapped": unmapped, "no_applicable": no_applicable}


# ---------------------------------------------------------------- diff 基准
def _scan_item(path, report, identity, content_sha256):
    return ScanItem(
        path=path, kind=KIND_CARD, identity=identity, content_sha256=content_sha256,
        card_id=report.card_id, carrier=report.carrier, grade=report.grade, report=report,
    )


def _pick_field(ruleset, carrier, scenario, severities=None, check_type=None):
    """从规则库挑一个隐式字段（可按严重度集或 check_type 过滤）；无则 ``None``。"""
    for field in implicit_targets_for(ruleset, carrier, scenario):
        if severities is not None:
            if severities_for(ruleset, OBSERVED_IMPLICIT, field, carrier, scenario) != severities:
                continue
        if check_type is not None:
            if rule_of_type(ruleset, OBSERVED_IMPLICIT, field, check_type,
                            carrier, scenario) is None:
                continue
        return field
    return None


def _two_rounds(ruleset):
    """构造两轮扫描输入与期望（覆盖全部对账集合）。"""
    carrier = "text"
    scenario = SCENARIO_AUTHORED
    fields = implicit_targets_for(ruleset, carrier, scenario)
    critical_field = _pick_field(ruleset, carrier, scenario, severities=["critical"]) or fields[0]
    minor_field = _pick_field(ruleset, carrier, scenario, severities=["minor"]) or fields[-1]

    good = full_implicit(ruleset, carrier, scenario)
    bad_critical = dict(good)
    bad_critical.pop(critical_field, None)
    bad_minor = dict(good)
    bad_minor.pop(minor_field, None)

    round1 = [
        ("card:A", "A", bad_critical, "sha-a-1"),
        ("card:B", "B", good, "sha-b-1"),
        ("card:C", "C", bad_critical, "sha-c-1"),
        ("card:D", "D", good, "sha-d-1"),
    ]
    round2 = [
        ("card:A", "A", good, "sha-a-2"),          # 已修复
        ("card:B", "B", good, "sha-b-2"),          # 稳定（指纹变了 → content_changed）
        ("card:C", "C", bad_minor, "sha-c-1"),     # 持续违规（fail 目标集变了）
        ("card:E", "E", bad_critical, "sha-e-1"),  # 新增违规
        ("card:F", "F", good, "sha-f-1"),          # 新增合规件
    ]
    return {
        "carrier": carrier,
        "scenario": scenario,
        "round1": round1,
        "round2": round2,
        "expect_mixed": {
            "added": ["card:E"],
            "fixed": ["card:A"],
            "persistent": ["card:C"],
            "stable": ["card:B"],
            "new_items": ["card:F"],
            "removed": ["card:D"],
            # A 是"已修复"（修复即改内容 → 指纹必变）；B 是"稳定但内容被改动"
            "content_changed": ["card:A", "card:B"],
            "changed_targets": {"card:C": sorted([critical_field, minor_field])},
        },
        "expect_identical": {
            "added": [],
            "fixed": [],
            "persistent": ["card:A", "card:C"],
            "stable": ["card:B", "card:D"],
            "new_items": [],
            "removed": [],
            "content_changed": [],
            "changed_targets": {},
        },
    }


def _build_scan(entries, ruleset, data_dir, carrier, scenario):
    items = []
    for identity, card_id, implicit, fingerprint in entries:
        card = valid_card(ruleset, card_id, carrier, scenario)
        card["implicit"] = dict(implicit)
        report = check_card_dict(card, data_dir)
        items.append(_scan_item(
            "{0}.json".format(card_id.lower()), report, identity,
            sha256_text("bench-sha::{0}".format(fingerprint))))
    return ScanResult(items=items, generated_at="", ruleset_coordinate=ruleset.coordinate)


def diff_scenarios(ruleset, data_dir):
    """两轮对账的确定性算例（FR-11 的 ``diff`` 基准）。

    :returns: ``[(scenario_id, description, previous, current, expect), …]``
        - ``expect``：全部对账集合（三类主集合 + 辅助集合）的**完全一致**声明
          （"三类集合完全一致"的验收口径），另含 ``changed_targets``。
    """
    plan = _two_rounds(ruleset)
    if not plan["round1"]:
        return []

    carrier = plan["carrier"]
    scenario = plan["scenario"]
    previous = _build_scan(plan["round1"], ruleset, data_dir, carrier, scenario)
    current = _build_scan(plan["round2"], ruleset, data_dir, carrier, scenario)
    identical = _build_scan(plan["round1"], ruleset, data_dir, carrier, scenario)

    return [
        ("DIFF-MIXED",
         "两轮混合变动：新增违规/已修复/持续违规/稳定/新增件/移除/内容变动全覆盖",
         previous, current, plan["expect_mixed"]),
        ("DIFF-IDENTICAL",
         "两轮完全相同 → 持续违规件保持持续、稳定件保持稳定，无新增/无移除/无内容变动",
         previous, identical, plan["expect_identical"]),
    ]


def diff_result(previous, current, generated_at=""):
    """跑一次对账（供基准与测试共用同一入口）。"""
    return diff_scans(previous, current, generated_at=generated_at)


# ---------------------------------------------------------------- 用例判定
def _has_finding(report, item):
    for finding in findings_for(report, item["scope"]):
        if (finding.target == item["target"] and finding.status == item["status"]
                and finding.code == item["code"]):
            return True
    return False


def check_field_case(case, data_dir):
    """跑一条 ``fields`` 用例，返回不一致描述列表（空 = 通过）。"""
    report = check_card_dict(case["card"], data_dir)
    mismatches = []
    for item in case.get("expect", []):
        if not _has_finding(report, item):
            mismatches.append("缺期望判定 {0}:{1} {2}/{3}".format(
                item["scope"], item["target"], item["status"], item["code"] or "(无码)"))
    for item in case.get("forbid", []):
        if _has_finding(report, item):
            mismatches.append("出现禁止判定 {0}:{1} {2}/{3}".format(
                item["scope"], item["target"], item["status"], item["code"] or "(无码)"))
    expected_grade = case.get("expect_grade")
    if expected_grade is not None and report.grade != expected_grade:
        mismatches.append("等级 {0} != 期望 {1}".format(report.grade, expected_grade))
    return mismatches


def check_constructed_case(case, data_dir):
    """跑一条 ``constructed`` 用例，返回不一致描述列表（空 = 通过）。"""
    report = check_card_dict(case["card"], data_dir)
    mismatches = []

    for scope in SCOPE_ORDER:
        declared = sorted(set(case["expect_fail"].get(scope, []) or []))
        actual = observed_fail(report, scope)
        if actual is not None and actual != declared:
            mismatches.append("{0} fail 集合 {1} != 期望 {2}".format(scope, actual, declared))

    mismatches.extend(compare_nonpass(report, case["expect_nonpass"]))

    expected_grade = case.get("expect_grade")
    if expected_grade is not None and report.grade != expected_grade:
        mismatches.append("等级 {0} != 期望 {1}".format(report.grade, expected_grade))
    return mismatches


def check_diff_scenario(scenario):
    """跑一条 ``diff`` 用例，返回不一致描述列表（空 = 通过）。"""
    _scenario_id, _description, previous, current, expect = scenario
    diff = diff_result(previous, current)
    mismatches = []

    for name in DIFF_COLLECTIONS:
        declared = sorted(expect.get(name, []) or [])
        actual = sorted(entry.identity for entry in getattr(diff, name))
        if actual != declared:
            mismatches.append("{0} 集合 {1} != 期望 {2}".format(name, actual, declared))

    for identity, targets in (expect.get("changed_targets") or {}).items():
        entry = None
        for candidate in diff.persistent:
            if candidate.identity == identity:
                entry = candidate
                break
        if entry is None:
            mismatches.append("持续违规件 {0} 缺失（无从核对目标集变化）".format(identity))
            continue
        actual_targets = sorted(entry.changed_targets)
        if actual_targets != sorted(targets):
            mismatches.append("{0} 变化目标集 {1} != 期望 {2}".format(
                identity, actual_targets, sorted(targets)))
    return mismatches


def load_ruleset_and_mapping(data_dir):
    """一次加载规则库与映射表（基准与测试共用，避免各自加载口径不同）。"""
    return effective_ruleset(data_dir), load_mapping_table(data_dir)


__all__ = [
    "SCOPE_ORDER", "NONPASS_STATUSES", "DIFF_COLLECTIONS", "OUT_OF_SET", "NEUTRAL_TEXT",
    "findings_for", "observed_nonpass", "observed_fail", "compare_nonpass",
    "explicit_targets_for", "implicit_targets_for", "rule_of_type", "pattern_fragments",
    "allowed_values", "severities_for", "unique_rule", "grade_for_fail_severities",
    "make_card", "valid_implicit_value", "explicit_element", "full_implicit", "valid_card",
    "field_key", "alias_key",
    "field_cases", "missing_check_types", "constructed_cases", "truth_library_cases",
    "synthetic_mapped_field", "synthetic_unmapped_target", "build_synthetic_data_dirs",
    "diff_scenarios", "diff_result",
    "check_field_case", "check_constructed_case", "check_diff_scenario",
    "load_ruleset_and_mapping",
]