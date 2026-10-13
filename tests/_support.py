"""测试共用夹具构造器。

**不依赖仓库真实数据**：全部用例在临时目录里构造"带指定 status 的规则库/映射表"，
这样门控、引擎、退出码各条路径都能确定性地被覆盖（仓库 M0 数据是全 pending 的）。
"""

from pathlib import Path

from labelcheck.jsonio import write_json


#: 保留域（示例用），不产生真实邮箱依赖
SOURCE_URL = "https://example.invalid/spec"


def make_rule(rule_id, **overrides):
    """构造一条规则 JSON（默认 pending 占位），overrides 覆盖任意字段。"""
    base = {
        "rule_id": rule_id,
        "scope": "implicit",
        "carrier": [],
        "target": "content_property",
        "check_type": "presence",
        "params": {},
        "severity": "major",
        "only_if": {},
        "clause": {"article": "第9条", "excerpt": "占位要点"},
        "status": "pending",
        "source_url": SOURCE_URL,
        "verified_at": None,
    }
    base.update(overrides)
    return base


def make_mapping_field(national_field, aliases=None, status="pending", **overrides):
    base = {
        "national_field": national_field,
        "label": national_field,
        "aliases": list(aliases) if aliases else [],
        "status": status,
        "source_url": SOURCE_URL,
        "clause": {"article": "第9条", "excerpt": "占位要点"},
    }
    base.update(overrides)
    return base


DEFAULT_MAPPING = [
    make_mapping_field("content_property", ["content.property"], status="verified"),
    make_mapping_field("service_provider_name", ["service.provider.name"], status="verified"),
    make_mapping_field("service_provider_code", ["service.provider.code"], status="verified"),
    make_mapping_field("content_id", ["content.id"], status="verified"),
]


def build_data_dir(root, docs, active=None, mapping_fields=None, mapping=True):
    """在 ``root`` 下构造一个数据目录。

    :param docs: ``{doc_id: {"version":..., "status":..., "rules":[...], "sha256":...}}``
    :param active: ``{doc_id: version}``；默认取每个 doc 的 version
    :param mapping_fields: 映射表字段列表；默认 :data:`DEFAULT_MAPPING`
    :returns: ``pathlib.Path``（数据根，含 rules/ 与 mapping/）
    """
    root = Path(root)
    documents = []
    active_map = {}

    for doc_id, spec in docs.items():
        version = spec.get("version", "2025-09-01")
        doc_status = spec.get("status", "pending")
        rules = spec.get("rules", [])
        rules_file = "{0}/{1}.json".format(doc_id, version)

        write_json(
            root / "rules" / doc_id / "{0}.json".format(version),
            {
                "schema_version": 1,
                "doc_id": doc_id,
                "version": version,
                "rules": rules,
            },
        )

        version_entry = {
            "version": version,
            "effective_from": version,
            "rules_file": rules_file,
            "status": doc_status,
            "source_url": SOURCE_URL,
        }
        if "sha256" in spec:
            version_entry["sha256"] = spec["sha256"]
        else:
            version_entry["sha256"] = None

        documents.append({
            "doc_id": doc_id,
            "title": spec.get("title", doc_id),
            "doc_number": spec.get("doc_number", doc_id),
            "kind": spec.get("kind", "measure"),
            "issuer": spec.get("issuer", "示例发布机关"),
            "effective_from": version,
            "status": doc_status,
            "source_url": SOURCE_URL,
            "versions": [version_entry],
        })
        active_map[doc_id] = spec.get("active_version", version)

    if active is not None:
        active_map.update(active)

    write_json(root / "rules" / "registry.json", {
        "schema_version": 1,
        "documents": documents,
        "active": active_map,
    })

    if mapping:
        write_json(root / "mapping" / "national-fields.json", {
            "schema_version": 1,
            "profiles": {},
            "fields": DEFAULT_MAPPING if mapping_fields is None else mapping_fields,
        })

    return root


def make_card(**overrides):
    """构造一张合法标识卡 dict。"""
    base = {
        "card_id": "SYN-TEST-0001",
        "carrier": "text",
        "content_sha256": "a" * 64,
        "source": "synthetic",
        "explicit": [],
        "implicit": {},
        "notes": "",
    }
    base.update(overrides)
    return base


#: 全 verified 的文档 + 规则数据目录预设（供引擎/分级用例）
def verified_docs(rules=None):
    return {
        "sample-doc": {
            "version": "2025-09-01",
            "status": "verified",
            "rules": rules if rules is not None else [],
        }
    }
