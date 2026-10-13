"""字段映射引擎测试（确定性归一 + 歧义检测）。"""

import pytest

from labelcheck.errors import RulesetError
from labelcheck.jsonio import write_json
from labelcheck.mapping import load_mapping_table, resolve_fields

from _support import build_data_dir, make_mapping_field


def _table(tmp_path, fields):
    data = build_data_dir(tmp_path / "d", {"d": {"status": "pending", "rules": []}}, mapping_fields=fields)
    return load_mapping_table(data)


def test_direct_name_hit(tmp_path):
    table = _table(tmp_path, [make_mapping_field("content_property", ["content.property"])])
    result = resolve_fields({"content_property": "AI_GENERATED"}, table)
    assert result["content_property"].found
    assert result["content_property"].value == "AI_GENERATED"
    assert result["content_property"].matched_key == "content_property"


def test_alias_hit(tmp_path):
    table = _table(tmp_path, [make_mapping_field("content_property", ["content.property"])])
    result = resolve_fields({"content.property": "AI_SYNTHETIC"}, table)
    res = result["content_property"]
    assert res.found and res.value == "AI_SYNTHETIC" and res.matched_key == "content.property"


def test_declaration_order_decides_when_multiple_aliases_hit(tmp_path):
    """多别名同时命中 → 取声明序最先者，其余记入 alternatives（不静默丢弃）。"""
    table = _table(tmp_path, [
        make_mapping_field("content_property", ["first.key", "second.key"]),
    ])
    result = resolve_fields({"second.key": "B", "first.key": "A"}, table)
    res = result["content_property"]
    assert res.matched_key == "first.key"
    assert res.value == "A"
    assert res.alternatives == ["second.key"]


def test_direct_name_beats_alias(tmp_path):
    """国标字段名自身优先于别名（keys = [name] + aliases，声明序）。"""
    table = _table(tmp_path, [make_mapping_field("content_property", ["content.property"])])
    result = resolve_fields({"content_property": "DIRECT", "content.property": "ALIAS"}, table)
    res = result["content_property"]
    assert res.matched_key == "content_property"
    assert res.value == "DIRECT"
    assert res.alternatives == ["content.property"]


def test_missing_field_resolves_to_not_found(tmp_path):
    table = _table(tmp_path, [make_mapping_field("content_property", ["content.property"])])
    result = resolve_fields({}, table)
    assert not result["content_property"].found
    assert result["content_property"].value is None


def test_result_key_order_follows_mapping_declaration(tmp_path):
    fields = [
        make_mapping_field("zeta", ["z"]),
        make_mapping_field("alpha", ["a"]),
    ]
    table = _table(tmp_path, fields)
    result = resolve_fields({}, table)
    assert list(result.keys()) == ["zeta", "alpha"], "键序须为映射表声明序（非排序/非 set 序）"


def test_ambiguous_key_across_fields_is_rejected(tmp_path):
    """同一容器键映射到两个国标字段 = 映射表缺陷，必须报错而非猜测。"""
    fields = [
        make_mapping_field("f1", ["shared.key"]),
        make_mapping_field("f2", ["shared.key"]),
    ]
    with pytest.raises(RulesetError) as excinfo:
        _table(tmp_path, fields)
    assert "歧义" in str(excinfo.value)


def test_duplicate_national_field_rejected(tmp_path):
    fields = [make_mapping_field("same"), make_mapping_field("same", ["other"])]
    with pytest.raises(RulesetError) as excinfo:
        _table(tmp_path, fields)
    assert "重复" in str(excinfo.value)


def test_bad_status_rejected(tmp_path):
    fields = [make_mapping_field("f1", status="maybe")]
    with pytest.raises(RulesetError):
        _table(tmp_path, fields)


def test_missing_mapping_file_raises(tmp_path):
    data = build_data_dir(tmp_path / "d", {"d": {"status": "pending", "rules": []}}, mapping=False)
    with pytest.raises(RulesetError):
        load_mapping_table(data)


def test_shipped_mapping_table_is_gated(data_dir):
    """M0 随附映射表全部 pending（M1 按原文核对后转 verified）。"""
    table = load_mapping_table(data_dir)
    assert len(table) >= 4
    assert table.verified_field_count == 0
    assert table.pending_field_count == len(table)


def test_mapping_counts(tmp_path):
    fields = [
        make_mapping_field("f1", status="verified"),
        make_mapping_field("f2", status="pending"),
    ]
    table = _table(tmp_path, fields)
    assert table.verified_field_count == 1
    assert table.pending_field_count == 1
