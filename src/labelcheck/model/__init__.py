"""统一中间表示（UMR）：标识卡、判定结果与报告对象的**纯数据模型**。

设计契约见 plan/04-模块详设.md §一。字段名与枚举值属**既定口径**（plan/04 §十一），
后续里程碑不得漂移。

本模块**零业务逻辑**：只做结构定义、构造与输入校验（把畸形输入挡在判定路径之前）。
"""

import re

from .. import DISCLAIMER as _DISCLAIMER
from ..errors import InputError

#: 载体枚举（既定口径）
CARRIERS = ("text", "image", "audio", "video")

#: 输入来源枚举
SOURCES = ("synthetic", "manual", "parsed")

#: 适用场景枚举（**输入契约**，M2 新增；语义见 plan/04 §五.4）。
#:
#: - ``authored``   —— 服务提供者产出/交付的内容（默认；办法第四/五条、国标 §5、§6.1 a) 1)–3)）
#: - ``exported``   —— 向用户提供下载/复制/导出（办法第四条第二款：导出文件须含显式标识）
#: - ``propagated`` —— 由网络信息内容传播服务发布/转发（办法第六条 + 国标 §6.1 a) 4) 5)）
#:
#: 场景是**适用性画像的输入**：规则以 ``only_if.scenario`` 声明适用场景，不适用 →
#: ``skipped``（不是 ``fail``）。一次核验只取一个场景（确定性；多场景须分别核验）。
SCENARIO_AUTHORED = "authored"
SCENARIO_EXPORTED = "exported"
SCENARIO_PROPAGATED = "propagated"
SCENARIOS = (SCENARIO_AUTHORED, SCENARIO_EXPORTED, SCENARIO_PROPAGATED)

#: 观测作用域键（**输入契约**，M2 新增）：该 scope 的数据是否**确实被观测到**。
#:
#: 手工/上游系统录入的标识卡两个 scope 都算已观测；**容器解析通路**只可能观测到隐式
#: （文件元数据），显式标识是渲染后画面上的文字/语音，解析器看不到 → 显式作用域
#: ``observed=False``，引擎对该 scope 一律判 ``unknown``（**绝不臆测合规或违规**）。
OBSERVED_EXPLICIT = "explicit"
OBSERVED_IMPLICIT = "implicit"
OBSERVED_KEYS = (OBSERVED_EXPLICIT, OBSERVED_IMPLICIT)

#: 判定状态枚举（语义见 plan/04 §一.3）
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_UNKNOWN = "unknown"
STATUS_SKIPPED = "skipped"
STATUSES = (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN, STATUS_SKIPPED)

#: 合规等级枚举（语义见 plan/04 §六）
GRADE_COMPLIANT = "compliant"
GRADE_PARTIAL = "partial"
GRADE_NON_COMPLIANT = "non_compliant"
#: 未评估：**没有任何生效规则可施加**（如规则库条目全部 pending）。
#: 与 compliant 严格区分——"没查出问题"与"没检查过"不是一回事，绝不输出假合规。
GRADE_NOT_ASSESSED = "not_assessed"

#: 严重度枚举
SEVERITY_CRITICAL = "critical"
SEVERITY_MAJOR = "major"
SEVERITY_MINOR = "minor"
SEVERITIES = (SEVERITY_CRITICAL, SEVERITY_MAJOR, SEVERITY_MINOR)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LabelCard(object):
    """标识卡：显式要素 + 隐式字段字典（核验器的统一输入）。

    :param card_id: 件唯一标识（必填、非空）
    :param carrier: 载体，∈ :data:`CARRIERS`
    :param content_sha256: 内容指纹（64 位小写 hex）；缺失/不合法 → 输入非法
    :param explicit: 显式要素列表，每项为 dict（``element``/``present``/``position``/...）
    :param implicit: 隐式字段字典（容器原始键 → 值）
    :param source: 来源，∈ :data:`SOURCES`（默认 ``manual``）
    :param notes: 人工备注（不参与判定）
    :param scenario: 适用场景，∈ :data:`SCENARIOS`（默认 ``authored``；见 plan/04 §五.4）
    :param observed: 观测作用域 ``{scope: bool}``（默认两个 scope 均已观测）；
        ``observed[scope] = False`` → 该 scope 一律判 ``unknown``（解析通路看不到显式标识）
    :param implicit_duplicate_keys: 被观测到**出现多于一次**的容器键（GB 45438-2025 §6.1 c)
        「应仅保留一份文件元数据隐式标识」）；解析通路据实登记，手工录入也可声明。
    """

    __slots__ = ("card_id", "carrier", "content_sha256", "explicit", "implicit",
                 "source", "notes", "scenario", "observed", "implicit_duplicate_keys")

    #: 未声明场景时的默认值（办法第四/五条 + 国标 §5/§6.1 面向服务提供者产出内容）
    DEFAULT_SCENARIO = SCENARIO_AUTHORED
    #: 未声明观测作用域时的默认值（手工录入的标识卡两个 scope 都算已观测）
    DEFAULT_OBSERVED = {OBSERVED_EXPLICIT: True, OBSERVED_IMPLICIT: True}

    def __init__(self, card_id, carrier, content_sha256, explicit=None, implicit=None,
                 source="manual", notes="", scenario=None, observed=None,
                 implicit_duplicate_keys=None):
        self.card_id = card_id
        self.carrier = carrier
        self.content_sha256 = content_sha256
        self.explicit = list(explicit) if explicit else []
        self.implicit = dict(implicit) if implicit else {}
        self.source = source
        self.notes = notes
        self.scenario = self.DEFAULT_SCENARIO if scenario is None else scenario
        if self.scenario not in SCENARIOS:
            raise ValueError("非法 scenario：{0!r}（须为 {1}）".format(
                self.scenario, "/".join(SCENARIOS)))
        self.observed = self._normalize_observed(observed)
        self.implicit_duplicate_keys = list(implicit_duplicate_keys or [])

    @classmethod
    def _normalize_observed(cls, observed):
        """把 ``observed`` 归一为两个 scope 齐全的布尔字典（缺省视为已观测）。"""
        result = dict(cls.DEFAULT_OBSERVED)
        if observed is None:
            return result
        if not isinstance(observed, dict):
            raise ValueError("observed 必须是对象（scope → bool）")
        for key in observed:
            if key not in OBSERVED_KEYS:
                raise ValueError("observed 含未知 scope：{0!r}（须为 {1}）".format(
                    key, "/".join(OBSERVED_KEYS)))
        for key, value in observed.items():
            result[key] = bool(value)
        return result

    def observes(self, scope):
        """该 scope 的数据是否确实被观测到（解析通路对显式标识为 False）。"""
        return bool(self.observed.get(scope, True))

    # ------------------------------------------------------------------ 校验
    @classmethod
    def from_dict(cls, data):
        """从 dict 构造并**校验**；不合法抛 :class:`InputError`（exit 2）。"""
        if not isinstance(data, dict):
            raise InputError("标识卡必须是 JSON 对象，得到 {0}".format(type(data).__name__))

        card_id = data.get("card_id")
        if not isinstance(card_id, str) or not card_id.strip():
            raise InputError("标识卡缺少合法 card_id（须为非空字符串）")

        carrier = data.get("carrier")
        if carrier not in CARRIERS:
            raise InputError(
                "标识卡 {0} 的 carrier 非法：{1!r}（须为 {2} 之一）".format(
                    card_id, carrier, "/".join(CARRIERS)
                )
            )

        content_sha256 = data.get("content_sha256")
        if not isinstance(content_sha256, str) or not _SHA256_RE.match(content_sha256):
            raise InputError(
                "标识卡 {0} 的 content_sha256 缺失或不合法（须为 64 位小写 hex）".format(card_id)
            )

        source = data.get("source", "manual")
        if source not in SOURCES:
            raise InputError(
                "标识卡 {0} 的 source 非法：{1!r}（须为 {2} 之一）".format(
                    card_id, source, "/".join(SOURCES)
                )
            )

        scenario = data.get("scenario", cls.DEFAULT_SCENARIO)
        if scenario not in SCENARIOS:
            raise InputError(
                "标识卡 {0} 的 scenario 非法：{1!r}（须为 {2} 之一）".format(
                    card_id, scenario, "/".join(SCENARIOS)
                )
            )

        observed = data.get("observed", None)
        if observed is not None:
            if not isinstance(observed, dict):
                raise InputError("标识卡 {0} 的 observed 必须是对象（scope → bool）".format(card_id))
            for key in observed:
                if key not in OBSERVED_KEYS:
                    raise InputError(
                        "标识卡 {0} 的 observed 含未知 scope：{1!r}（须为 {2}）".format(
                            card_id, key, "/".join(OBSERVED_KEYS)))
            for key, value in observed.items():
                if not isinstance(value, bool):
                    raise InputError(
                        "标识卡 {0} 的 observed[{1}] 必须是布尔值".format(card_id, key))

        explicit = data.get("explicit", [])
        if not isinstance(explicit, list):
            raise InputError("标识卡 {0} 的 explicit 必须是数组".format(card_id))
        for index, item in enumerate(explicit):
            if not isinstance(item, dict):
                raise InputError(
                    "标识卡 {0} 的 explicit[{1}] 必须是对象".format(card_id, index)
                )
            if not isinstance(item.get("element"), str) or not item["element"]:
                raise InputError(
                    "标识卡 {0} 的 explicit[{1}] 缺少合法 element".format(card_id, index)
                )

        implicit = data.get("implicit", {})
        if not isinstance(implicit, dict):
            raise InputError("标识卡 {0} 的 implicit 必须是对象".format(card_id))

        duplicate_keys = data.get("implicit_duplicate_keys", [])
        if duplicate_keys is None:
            duplicate_keys = []
        if not isinstance(duplicate_keys, list) or any(
                not isinstance(k, str) or not k for k in duplicate_keys):
            raise InputError(
                "标识卡 {0} 的 implicit_duplicate_keys 必须是非空字符串数组".format(card_id))

        notes = data.get("notes", "")
        if notes is None:
            notes = ""
        if not isinstance(notes, str):
            raise InputError("标识卡 {0} 的 notes 必须是字符串".format(card_id))

        return cls(
            card_id=card_id,
            carrier=carrier,
            content_sha256=content_sha256,
            explicit=explicit,
            implicit=implicit,
            source=source,
            notes=notes,
            scenario=scenario,
            observed=observed,
            implicit_duplicate_keys=duplicate_keys,
        )

    # ------------------------------------------------------------------ 查询
    def find_explicit(self, element_id):
        """按 element id 取显式要素（返回首个匹配的 dict，无则 None）。"""
        for item in self.explicit:
            if item.get("element") == element_id:
                return item
        return None

    def to_dict(self):
        """回写为 dict（顺序固定，保证规范化输出可复现）。"""
        return {
            "card_id": self.card_id,
            "carrier": self.carrier,
            "content_sha256": self.content_sha256,
            "source": self.source,
            "scenario": self.scenario,
            "observed": {key: self.observed[key] for key in OBSERVED_KEYS},
            "explicit": [dict(item) for item in self.explicit],
            "implicit": dict(self.implicit),
            "implicit_duplicate_keys": list(self.implicit_duplicate_keys),
            "notes": self.notes,
        }

    def __repr__(self):
        return "LabelCard(card_id={0!r}, carrier={1!r}, scenario={2!r}, explicit={3}, implicit={4})".format(
            self.card_id, self.carrier, self.scenario, len(self.explicit), len(self.implicit)
        )


class Finding(object):
    """逐要素/逐字段判定（契约见 plan/04 §一.3）。

    :param scenario: 该判定所属场景（见 :data:`SCENARIOS`）；``skipped`` 判定记录
        "因何场景不适用"，故场景随判定固化（不放进报告头，避免遮蔽单条来源）。
    """

    __slots__ = ("scope", "target", "status", "code", "message", "clause", "evidence",
                 "severity", "scenario")

    def __init__(self, scope, target, status, code="", message="", clause=None, evidence=None,
                 severity="major", scenario=SCENARIO_AUTHORED):
        if status not in STATUSES:
            raise ValueError("非法 status：{0!r}".format(status))
        if severity not in SEVERITIES:
            raise ValueError("非法 severity：{0!r}".format(severity))
        self.scope = scope
        self.target = target
        self.status = status
        self.code = code
        self.message = message
        self.clause = dict(clause) if clause else {}
        self.evidence = dict(evidence) if evidence else {}
        self.severity = severity
        self.scenario = scenario

    @property
    def is_violation(self):
        """是否计入违规（``fail`` 是；``unknown`` 否，见 plan/04 §一.3）。"""
        return self.status == STATUS_FAIL

    @property
    def needs_review(self):
        """是否需人工确认（``unknown``）。"""
        return self.status == STATUS_UNKNOWN

    def to_dict(self):
        return {
            "scope": self.scope,
            "target": self.target,
            "status": self.status,
            "severity": self.severity,
            "scenario": self.scenario,
            "code": self.code,
            "message": self.message,
            "clause": dict(self.clause),
            "evidence": dict(self.evidence),
        }

    def __repr__(self):
        return "Finding({0}:{1} → {2}{3})".format(
            self.scope, self.target, self.status,
            " [{0}]".format(self.code) if self.code else "",
        )


class CheckReport(object):
    """单件核验报告（契约见 plan/04 §一.2）。"""

    __slots__ = ("card_id", "carrier", "ruleset_coordinate", "documents",
                 "verified_rule_count", "pending_rule_count",
                 "explicit", "implicit", "grade", "missing", "errors",
                 "disclaimer", "content_sha256", "generated_at",
                 "scenario", "source", "observed")

    DISCLAIMER = _DISCLAIMER

    def __init__(self, card_id, carrier, ruleset_coordinate="",
                 documents=None, verified_rule_count=0, pending_rule_count=0,
                 explicit=None, implicit=None, grade=GRADE_PARTIAL,
                 missing=None, errors=None, content_sha256="",
                 generated_at="", disclaimer=None,
                 scenario=SCENARIO_AUTHORED, source="manual", observed=None):
        self.card_id = card_id
        self.carrier = carrier
        self.ruleset_coordinate = ruleset_coordinate
        self.documents = list(documents) if documents else []
        self.verified_rule_count = verified_rule_count
        self.pending_rule_count = pending_rule_count
        self.explicit = list(explicit) if explicit else []
        self.implicit = list(implicit) if implicit else []
        self.grade = grade
        self.missing = list(missing) if missing else []
        self.errors = list(errors) if errors else []
        self.content_sha256 = content_sha256
        self.generated_at = generated_at
        self.disclaimer = self.DISCLAIMER if disclaimer is None else disclaimer
        self.scenario = scenario
        self.source = source
        self.observed = dict(observed) if observed else dict(LabelCard.DEFAULT_OBSERVED)

    @property
    def all_findings(self):
        """显式 + 隐式全部判定（顺序固定：显式在前）。"""
        return list(self.explicit) + list(self.implicit)

    @property
    def violations(self):
        return [f for f in self.all_findings if f.is_violation]

    @property
    def reviews(self):
        return [f for f in self.all_findings if f.needs_review]

    @property
    def skips(self):
        """因载体/场景不适用而未判定的条目（``skipped``）。"""
        return [f for f in self.all_findings if f.status == STATUS_SKIPPED]

    @property
    def has_violation(self):
        """是否存在 fail（决定 CLI 退出码 0/1）。"""
        return any(f.is_violation for f in self.all_findings)

    @property
    def unobserved_scopes(self):
        """未被观测到的作用域列表（解析通路通常含 ``explicit``）。"""
        return [key for key in OBSERVED_KEYS if not self.observed.get(key, True)]

    def to_dict(self):
        return {
            "card_id": self.card_id,
            "carrier": self.carrier,
            "source": self.source,
            "scenario": self.scenario,
            "observed": {key: bool(self.observed.get(key, True)) for key in OBSERVED_KEYS},
            "content_sha256": self.content_sha256,
            "generated_at": self.generated_at,
            "ruleset": {
                "coordinate": self.ruleset_coordinate,
                "documents": [dict(doc) for doc in self.documents],
                "verified_rule_count": self.verified_rule_count,
                "pending_rule_count": self.pending_rule_count,
            },
            "explicit": [f.to_dict() for f in self.explicit],
            "implicit": [f.to_dict() for f in self.implicit],
            "grade": self.grade,
            "missing": list(self.missing),
            "errors": list(self.errors),
            "disclaimer": self.disclaimer,
        }

    def __repr__(self):
        return "CheckReport(card_id={0!r}, grade={1!r}, findings={2}/{3})".format(
            self.card_id, self.grade, len(self.all_findings), len(self.violations)
        )


__all__ = [
    "CARRIERS", "SOURCES", "STATUSES", "SEVERITIES", "SCENARIOS", "OBSERVED_KEYS",
    "STATUS_PASS", "STATUS_FAIL", "STATUS_UNKNOWN", "STATUS_SKIPPED",
    "SCENARIO_AUTHORED", "SCENARIO_EXPORTED", "SCENARIO_PROPAGATED",
    "OBSERVED_EXPLICIT", "OBSERVED_IMPLICIT",
    "GRADE_COMPLIANT", "GRADE_PARTIAL", "GRADE_NON_COMPLIANT", "GRADE_NOT_ASSESSED",
    "SEVERITY_CRITICAL", "SEVERITY_MAJOR", "SEVERITY_MINOR",
    "LabelCard", "Finding", "CheckReport",
]
