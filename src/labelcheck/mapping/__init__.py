"""字段映射引擎：容器/元数据键 → 国标字段（契约见 plan/04 §五）。

映射表是**可配置、可版本化**的数据资产（``data/mapping/national-fields.json``），
M0 只建骨架表（字段条目全 ``pending``），M1 按 GB 45438-2025 原文填内容。

归一算法是**确定性**的：命中顺序由映射表**声明顺序**决定，不看 set/dict 迭代序；
多别名同时命中取声明序最先者，其余记入 ``alternatives``（不静默丢弃）。
"""

from pathlib import Path

from ..errors import RulesetError
from ..jsonio import load_json
from ..rules.rule import STATUS_VERIFIED, STATUS_PENDING, VERIFY_STATUSES

MAPPING_FILE = "mapping/national-fields.json"


class FieldMapping(object):
    """单个国标字段的映射定义。"""

    __slots__ = ("national_field", "label", "aliases", "status", "source_url", "clause")

    def __init__(self, national_field, label="", aliases=None, status=STATUS_PENDING,
                 source_url="", clause=None):
        self.national_field = national_field
        self.label = label
        self.aliases = list(aliases) if aliases else []
        self.status = status
        self.source_url = source_url
        self.clause = dict(clause) if clause else {}

    @property
    def keys(self):
        """全部候选键（国标字段名自身 + 别名），顺序固定 = 声明序。"""
        return [self.national_field] + self.aliases

    def __repr__(self):
        return "FieldMapping({0}, aliases={1}, status={2})".format(
            self.national_field, len(self.aliases), self.status
        )


class MappingTable(object):
    """字段映射表（含版本、容器画像与解析画像）。"""

    def __init__(self, fields, schema_version=1, warnings=None, profiles=None,
                 parse_profile=None):
        self.fields = list(fields)
        self.schema_version = schema_version
        self.warnings = list(warnings) if warnings else []
        self.profiles = dict(profiles) if profiles else {}
        self.parse_profile = dict(parse_profile) if parse_profile else {}

    @property
    def payload_wrapper(self):
        """隐式标识 JSON 载荷的外层包裹键（附录 E b)；无配置则返回空串。"""
        value = self.parse_profile.get("payload_wrapper", "")
        return value if isinstance(value, str) else ""

    def __len__(self):
        return len(self.fields)

    def __iter__(self):
        return iter(self.fields)

    def by_field(self, national_field):
        for item in self.fields:
            if item.national_field == national_field:
                return item
        return None

    @property
    def verified_field_count(self):
        return sum(1 for f in self.fields if f.status == STATUS_VERIFIED)

    @property
    def pending_field_count(self):
        return sum(1 for f in self.fields if f.status != STATUS_VERIFIED)


class Resolution(object):
    """单个国标字段的归一结果。"""

    __slots__ = ("national_field", "value", "matched_key", "alternatives", "mapping")

    def __init__(self, national_field, value, matched_key=None, alternatives=None, mapping=None):
        self.national_field = national_field
        self.value = value
        self.matched_key = matched_key
        self.alternatives = list(alternatives) if alternatives else []
        self.mapping = mapping

    @property
    def found(self):
        return self.matched_key is not None

    @property
    def all_matched_keys(self):
        """该要素命中的**全部**容器键（声明序；命中键 = 主键 + 其余别名）。

        用于 ``unique`` 校验（GB 45438-2025 §6.1 c)：同一要素被多个容器键同时提供
        = 隐式标识被重复保留，不合规。
        """
        if self.matched_key is None:
            return []
        return [self.matched_key] + list(self.alternatives)

    def to_dict(self):
        return {
            "national_field": self.national_field,
            "value": self.value,
            "matched_key": self.matched_key,
            "alternatives": list(self.alternatives),
        }

    def __repr__(self):
        return "Resolution({0} ← {1!r}{2})".format(
            self.national_field,
            self.matched_key,
            "" if not self.alternatives else " (+{0} alt)".format(len(self.alternatives)),
        )


def load_mapping_table(data_dir):
    """加载并校验映射表；结构缺陷抛 :class:`RulesetError`（exit 3）。"""
    path = Path(data_dir) / MAPPING_FILE
    data = load_json(path, error_cls=RulesetError)
    if not isinstance(data, dict):
        raise RulesetError("映射表必须是 JSON 对象：{0}".format(path))

    raw_fields = data.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise RulesetError("映射表的 fields 必须是非空数组：{0}".format(path))

    fields = []
    names = set()
    owned_keys = {}
    for index, raw in enumerate(raw_fields):
        if not isinstance(raw, dict):
            raise RulesetError("映射表 fields[{0}] 必须是对象".format(index))
        national_field = raw.get("national_field")
        if not isinstance(national_field, str) or not national_field:
            raise RulesetError("映射表 fields[{0}] 缺少合法 national_field".format(index))
        if national_field in names:
            raise RulesetError("映射表 national_field 重复：{0}".format(national_field))
        names.add(national_field)

        aliases = raw.get("aliases", []) or []
        if not isinstance(aliases, list) or any(not isinstance(a, str) or not a for a in aliases):
            raise RulesetError("映射表 {0} 的 aliases 必须是非空字符串数组".format(national_field))

        status = raw.get("status", STATUS_PENDING)
        if status not in VERIFY_STATUSES:
            raise RulesetError(
                "映射表 {0} 的 status 非法：{1!r}（须为 verified/pending）".format(national_field, status)
            )

        # 歧义检测：同一容器键不得映射到多个国标字段（映射表自身缺陷，不猜测）
        for key in [national_field] + list(aliases):
            owner = owned_keys.get(key)
            if owner is not None and owner != national_field:
                raise RulesetError(
                    "映射表歧义：容器键 {0!r} 同时映射到 {1} 与 {2}".format(key, owner, national_field)
                )
            owned_keys[key] = national_field

        fields.append(FieldMapping(
            national_field=national_field,
            label=raw.get("label", ""),
            aliases=aliases,
            status=status,
            source_url=raw.get("source_url", ""),
            clause=raw.get("clause", {}),
        ))

    return MappingTable(
        fields,
        schema_version=data.get("schema_version", 1),
        profiles=data.get("profiles", {}) or {},
        parse_profile=data.get("parse_profile", {}) or {},
    )


def resolve_fields(implicit, table):
    """把标识卡的 ``implicit`` 字典归一到国标字段。

    :param implicit: 容器原始键值字典
    :param table: :class:`MappingTable`
    :returns: ``{national_field: Resolution}``（键序 = 映射表声明序，确定性）

    算法（plan/04 §五.2）：按 ``keys`` 的声明顺序，取**第一个存在的键**；
    其余命中的键记入 ``alternatives``。
    """
    results = {}
    for mapping in table.fields:
        matched_key = None
        alternatives = []
        for key in mapping.keys:
            if key in implicit:
                if matched_key is None:
                    matched_key = key
                else:
                    alternatives.append(key)
        value = implicit.get(matched_key) if matched_key is not None else None
        results[mapping.national_field] = Resolution(
            national_field=mapping.national_field,
            value=value,
            matched_key=matched_key,
            alternatives=alternatives,
            mapping=mapping,
        )
    return results


__all__ = [
    "FieldMapping",
    "MappingTable",
    "Resolution",
    "load_mapping_table",
    "resolve_fields",
    "MAPPING_FILE",
]
