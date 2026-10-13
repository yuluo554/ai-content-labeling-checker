# -*- coding: utf-8 -*-
"""两轮扫描对账测试（FR-7，契约见 plan/04 §七）。

锁死四件事（对账正确性的核心）：

1. **四类集合**：新增违规 / 已修复 / 持续违规 / 稳定；辅助集合：新增件 / 移除件；
2. **稳定身份键**（plan/06 D28）：按 ``card:<card_id>`` / ``file:<相对路径>`` 配对，
   **不按**内容指纹——否则"已修复"永远检不出（修复 = 内容变 = 指纹变）；
3. **内容变动独立标记** ``content_changed``：身份不变而指纹变了要如实标出，
   且**不得**退化成"新增 + 移除"；
4. **确定性**：集合内件序固定（本轮序/上轮序），相同输入两次对账逐字节一致。
"""

import json
from pathlib import Path

import pytest

from labelcheck.model import LabelCard
from labelcheck.scan import (
    ScanItem, ScanResult, diff_scans, scan_paths, scan_target,
)
from labelcheck.scan.diff import (
    STATUS_ADDED, STATUS_FIXED, STATUS_PERSISTENT, STATUS_STABLE,
)

from _support import build_data_dir, make_card, make_mapping_field, make_rule

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


@pytest.fixture
def cases(tmp_path):
    path = tmp_path / "cases"
    path.mkdir()
    return path


@pytest.fixture
def data_dir(tmp_path):
    return build_data_dir(
        tmp_path / "data",
        {"doc": {"version": "2025-09-01", "status": "verified",
                 "rules": [make_rule("r", scope="implicit", target="content_property",
                                     check_type="presence", severity="critical",
                                     status="verified")]}},
        mapping_fields=[make_mapping_field("content_property", ["content.property"],
                                           status="verified")],
    )


def _write_card(path, **overrides):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(make_card(**overrides), ensure_ascii=False), encoding="utf-8")
    return path


def _scan(cases, data_dir):
    return scan_target(cases, data_dir)


# ------------------------------------------------------------------ 四类集合
def test_added_violation_detected(cases, data_dir):
    """上轮无此件 / 本轮新增违规 → added。"""
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    previous = _scan(cases, data_dir)

    _write_card(cases / "b.json", card_id="B", implicit={})  # 新增违规件
    current = _scan(cases, data_dir)

    diff = diff_scans(previous, current)
    assert [entry.card_id for entry in diff.added] == ["B"]
    assert diff.added[0].status == STATUS_ADDED
    assert diff.added[0].current_fail_targets == ["content_property"]
    assert diff.summary["added"] == 1


def test_existing_item_becomes_violation_is_added(cases, data_dir):
    """上轮合规、本轮违规（同一身份）→ 也计入 added（新增违规）。"""
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    previous = _scan(cases, data_dir)

    _write_card(cases / "a.json", card_id="A", implicit={})  # 同一 card_id，内容改为缺字段
    current = _scan(cases, data_dir)

    diff = diff_scans(previous, current)
    assert [entry.card_id for entry in diff.added] == ["A"]
    assert diff.added[0].previous_fail_targets == []
    assert diff.added[0].current_fail_targets == ["content_property"]


def test_fixed_violation_detected(cases, data_dir):
    """上轮违规、本轮合规 → fixed（**这正是选稳定身份键的理由**）。"""
    _write_card(cases / "a.json", card_id="A", implicit={})
    previous = _scan(cases, data_dir)

    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    current = _scan(cases, data_dir)

    diff = diff_scans(previous, current)
    assert [entry.card_id for entry in diff.fixed] == ["A"]
    assert diff.fixed[0].status == STATUS_FIXED
    assert diff.fixed[0].previous_fail_targets == ["content_property"]
    assert diff.fixed[0].current_fail_targets == []
    assert diff.summary["fixed"] == 1


def test_persistent_violation_detected(cases, data_dir):
    """两轮均违规 → persistent；fail 目标集变化记入 changed_targets。"""
    _write_card(cases / "a.json", card_id="A", implicit={})
    previous = _scan(cases, data_dir)
    current = _scan(cases, data_dir)

    diff = diff_scans(previous, current)
    assert [entry.card_id for entry in diff.persistent] == ["A"]
    assert diff.persistent[0].status == STATUS_PERSISTENT
    assert diff.persistent[0].changed_targets == []
    assert diff.summary["persistent"] == 1
    assert diff.summary["persistent_changed"] == 0


def test_stable_items_tracked(cases, data_dir):
    """两轮均合规 → stable。"""
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    previous = _scan(cases, data_dir)
    current = _scan(cases, data_dir)
    diff = diff_scans(previous, current)
    assert [entry.card_id for entry in diff.stable] == ["A"]
    assert diff.stable[0].status == STATUS_STABLE


def test_new_compliant_item_is_not_added_violation(cases, data_dir):
    """本轮新增且合规的件进 new_items，**不进** added（added 只装违规）。"""
    previous = _scan(cases, data_dir)  # 空目录
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    current = _scan(cases, data_dir)
    diff = diff_scans(previous, current)
    assert diff.added == []
    assert [entry.card_id for entry in diff.new_items] == ["A"]
    assert diff.summary["new_items"] == 1


def test_removed_item_tracked(cases, data_dir):
    """本轮不再出现的件进 removed（不静默丢）。"""
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    previous = _scan(cases, data_dir)
    (cases / "a.json").unlink()
    current = _scan(cases, data_dir)
    diff = diff_scans(previous, current)
    assert [entry.card_id for entry in diff.removed] == ["A"]
    assert diff.summary["removed"] == 1


# ------------------------------------------------------------------ 内容变动
def test_content_changed_is_flagged_without_identity_change(cases, data_dir):
    """身份不变而内容指纹变 → content_changed，且**不**退化成新增+移除。"""
    _write_card(cases / "a.json", card_id="A",
                content_sha256="a" * 64, implicit={"content.property": "AI"})
    previous = _scan(cases, data_dir)

    _write_card(cases / "a.json", card_id="A",
                content_sha256="b" * 64, implicit={"content.property": "AI"})
    current = _scan(cases, data_dir)

    diff = diff_scans(previous, current)
    assert diff.summary["content_changed"] == 1
    assert diff.content_changed[0].content_changed is True
    # 身份稳定：仍在 stable（既没消失也没新增）
    assert diff.added == [] and diff.removed == []
    assert [entry.card_id for entry in diff.stable] == ["A"]
    assert diff.stable[0].content_changed is True


def test_same_content_not_flagged_changed(cases, data_dir):
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    previous = _scan(cases, data_dir)
    current = _scan(cases, data_dir)
    diff = diff_scans(previous, current)
    assert diff.content_changed == []
    assert diff.stable[0].content_changed is False


# ------------------------------------------------------------------ 身份键口径（plan/06 D28）
def test_reconciliation_pairs_by_card_id_not_filename(cases, data_dir):
    """改文件名不改身份：改名不得误判为"新增 + 移除"。"""
    _write_card(cases / "old.json", card_id="A", implicit={})
    previous = _scan(cases, data_dir)

    (cases / "old.json").unlink()
    _write_card(cases / "new.json", card_id="A", implicit={"content.property": "AI"})
    current = _scan(cases, data_dir)

    diff = diff_scans(previous, current)
    assert diff.removed == [], "改名不应被当成移除"
    assert [entry.card_id for entry in diff.fixed] == ["A"], "改名后仍按 card_id 配对 → 修复被认出"


def test_parse_derived_card_id_is_stable_within_round(cases, data_dir):
    """解析件身份按相对路径（其 card_id 由内容派生，改内容会换 id）。"""
    import base64
    import sys
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from gen_parse import aigc_json, png_bytes

    (cases / "img.png").write_bytes(
        png_bytes([("tEXt", "XML:com.adobe.xmp", aigc_json())]))
    previous = _scan(cases, data_dir)
    assert previous.items[0].identity == "file:img.png"

    # 换内容（重写同一路径的字节）→ 身份不变、内容变动标记
    (cases / "img.png").write_bytes(
        png_bytes([("tEXt", "XML:com.adobe.xmp", aigc_json(label=None))]))
    current = _scan(cases, data_dir)
    diff = diff_scans(previous, current)
    assert diff.summary["content_changed"] == 1
    assert diff.removed == [], "同路径换内容不应被判成移除"
    assert [entry.identity for entry in diff.content_changed] == ["file:img.png"]


# ------------------------------------------------------------------ 失败件参与对账
def test_failed_item_fix_counts_as_fixed(cases, data_dir):
    """上轮失败件（scan_error）本轮成功且合规 → 计入 fixed（失败 → 成功）。"""
    (cases / "a.json").write_text("{not json", encoding="utf-8")
    previous = _scan(cases, data_dir)
    assert previous.summary["failed"] == 1

    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    current = _scan(cases, data_dir)
    diff = diff_scans(previous, current)
    # 身份从 file:a.json 变为 card:A —— 属于"移除 + 新增件"（身份类型不同）
    assert diff.summary["removed"] == 1
    assert diff.summary["new_items"] == 1


# ------------------------------------------------------------------ 确定性
def test_diff_is_deterministic(cases, data_dir):
    _write_card(cases / "a.json", card_id="A", implicit={})
    _write_card(cases / "b.json", card_id="B", implicit={"content.property": "AI"})
    previous = _scan(cases, data_dir)
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    _write_card(cases / "c.json", card_id="C", implicit={})
    current = _scan(cases, data_dir)

    first = diff_scans(previous, current).to_dict()
    second = diff_scans(previous, current).to_dict()
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == \
        json.dumps(second, ensure_ascii=False, sort_keys=True)


def test_diff_roundtrips_through_json(cases, data_dir):
    _write_card(cases / "a.json", card_id="A", implicit={})
    previous = _scan(cases, data_dir)
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    current = _scan(cases, data_dir)

    from labelcheck.scan.diff import DiffResult
    diff = diff_scans(previous, current)
    payload = diff.to_dict()
    restored = DiffResult.from_dict(json.loads(json.dumps(payload)))
    assert restored.summary == diff.summary
    assert [e.card_id for e in restored.fixed] == [e.card_id for e in diff.fixed]