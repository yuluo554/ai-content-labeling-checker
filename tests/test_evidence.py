# -*- coding: utf-8 -*-
"""证据链固化测试（FR-9，契约见 plan/04 §八.3）。

FR-9 是"系列招牌"：核查结论要能**复现对照**——故证据链必须固化到"报告被改动即可检出"
的程度。本文件锁死三件事（与 ``test_report.py`` 的报告骨架测试互补）：

1. **每件内容指纹随结果固化**：``evidence.json.items[*].content_sha256`` == 该件报告里的
   ``content_sha256``（证据链不断裂）；
2. **报告自身 sha256 进证据**：``evidence.json.report_sha256`` == ``report.md`` 的 sha256；
   报告被改动 → 与证据不符（对照复现）；
3. **产物清单哈希**：``artifacts{name→sha256}`` 覆盖全部产出（含 XLSX 二进制按字节计），
   且规则库坐标进证据（结论可归因到具体规则版本）。
"""

import json
from pathlib import Path

import pytest

from labelcheck.jsonio import sha256_bytes, sha256_text
from labelcheck.report import (
    DETAIL_CSV, EVIDENCE_JSON, REPORT_MD, REPORT_XLSX, SUMMARY_CSV,
    build_report, render_evidence, write_report,
)
from labelcheck.scan import scan_target

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
                 "title": "示例依据", "doc_number": "示例文号",
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


def _evidence(cases, data_dir, **kwargs):
    bundle = build_report(scan_target(cases, data_dir, **kwargs), generated_at="2026-01-01T00:00:00")
    return bundle, json.loads(bundle.files[EVIDENCE_JSON])


# ------------------------------------------------------------------ 内容指纹固化
def test_every_item_fingerprint_is_fixed_in_evidence(cases, data_dir):
    _write_card(cases / "a.json", card_id="A", content_sha256="1" * 64,
                implicit={"content.property": "AI"})
    _write_card(cases / "b.json", card_id="B", content_sha256="2" * 64, implicit={})
    bundle, evidence = _evidence(cases, data_dir)

    recorded = dict((item["card_id"], item["content_sha256"]) for item in evidence["items"])
    assert recorded == {"A": "1" * 64, "B": "2" * 64}


def test_evidence_fingerprint_matches_report_fingerprint(cases, data_dir):
    """证据里的指纹必须与该件报告里的指纹一致（证据链不断裂）。"""
    _write_card(cases / "a.json", card_id="A", content_sha256="9" * 64,
                implicit={"content.property": "AI"})
    scan = scan_target(cases, data_dir)
    bundle = build_report(scan, generated_at="2026-01-01T00:00:00")
    evidence = json.loads(bundle.files[EVIDENCE_JSON])
    assert evidence["items"][0]["content_sha256"] == scan.items[0].report.content_sha256


def test_failed_items_are_recorded_in_evidence(cases, data_dir):
    """失败件也进证据（记错误码），不静默消失。"""
    (cases / "broken.json").write_text("{not json", encoding="utf-8")
    manifest = cases / "list.lst"
    manifest.write_text("broken.json\n", encoding="utf-8")
    scan = scan_target(manifest, data_dir)
    bundle = build_report(scan, generated_at="2026-01-01T00:00:00")
    evidence = json.loads(bundle.files[EVIDENCE_JSON])
    record = evidence["items"][0]
    assert record["code"] == "scan_error"
    assert record["error"]


# ------------------------------------------------------------------ 报告自身指纹
def test_report_sha256_is_the_markdown_hash(cases, data_dir):
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    bundle, evidence = _evidence(cases, data_dir)
    assert evidence["report_sha256"] == sha256_text(bundle.files[REPORT_MD])


def test_evidence_artifacts_cover_all_outputs(cases, data_dir):
    """artifacts 清单须覆盖全部文本产物；XLSX 存在时按其字节计。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    bundle, evidence = _evidence(cases, data_dir)
    artifacts = evidence["artifacts"]
    for name in (REPORT_MD, SUMMARY_CSV, DETAIL_CSV):
        assert artifacts[name] == sha256_text(bundle.files[name])
    if REPORT_XLSX in bundle.files:
        assert artifacts[REPORT_XLSX] == sha256_bytes(bundle.files[REPORT_XLSX])


def test_tampering_with_any_artifact_is_detectable(cases, data_dir):
    """改动任一产物 → 与其在证据里的 sha256 不符。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    bundle, evidence = _evidence(cases, data_dir)
    for name in (REPORT_MD, SUMMARY_CSV, DETAIL_CSV):
        original = bundle.files[name]
        assert sha256_text(original) == evidence["artifacts"][name]
        assert sha256_text(original + "\n篡改\n") != evidence["artifacts"][name]


def test_evidence_records_ruleset_coordinate(cases, data_dir):
    """结论可归因到规则版本：证据须带规则库坐标与生效/待核对计数。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    _, evidence = _evidence(cases, data_dir)
    assert evidence["ruleset_coordinate"]
    assert evidence["verified_rule_count"] >= 1
    assert evidence["pending_rule_count"] >= 0


def test_evidence_carries_disclaimer(cases, data_dir):
    """免责声明随证据固化（结论口径不得因导出格式而丢失）。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    _, evidence = _evidence(cases, data_dir)
    assert "供参考" in evidence["disclaimer"]
    assert "不提供任何标识规避" in evidence["disclaimer"]


# ------------------------------------------------------------------ 落盘证据可对照
def test_written_evidence_matches_written_report(cases, data_dir, tmp_path):
    """落盘后：``evidence.json`` 里的 report_sha256 == 磁盘上 report.md 的 sha256。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    out = tmp_path / "out"
    write_report(scan_target(cases, data_dir), out, generated_at="2026-01-01T00:00:00")
    on_disk_report = (out / REPORT_MD).read_bytes()
    evidence = json.loads((out / EVIDENCE_JSON).read_text(encoding="utf-8"))
    assert evidence["report_sha256"] == sha256_bytes(on_disk_report)


def test_evidence_is_deterministic(cases, data_dir):
    """相同输入 + 相同时间戳 → 证据文件逐字节一致。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    first = build_report(scan_target(cases, data_dir), generated_at="2026-01-01T00:00:00")
    second = build_report(scan_target(cases, data_dir), generated_at="2026-01-01T00:00:00")
    assert first.files[EVIDENCE_JSON] == second.files[EVIDENCE_JSON]