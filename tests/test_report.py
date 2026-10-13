# -*- coding: utf-8 -*-
"""报告导出与证据链测试（FR-8 / FR-9，契约见 plan/04 §八）。

锁死五件事：

1. **格式齐备**：``report.md`` / ``summary.csv`` / ``detail.csv`` / ``evidence.json``
   恒产出；``report.xlsx`` 在 openpyxl 可用时产出（缺失时**降级 CSV 不崩**）；
2. **报告骨架**：报告头（时间/规则库坐标/生效计数）+ **强制免责声明** + 核查范围
   （含 M2 的 ``scenario``/``observed``/解析降级原因）+ 依据清单 + 逐件逐字段 + 违规清单 + 结论；
3. **证据链（FR-9）**：每件 ``content_sha256`` 固化；``evidence.json`` 含**报告自身 sha256**
   （改报告即可检出）；
4. **确定性（NFR-3）**：``generated_at`` 由调用方传入 → 相同输入两次导出**逐字节一致**
   （含 XLSX —— openpyxl 默认写系统时钟，已被钉死）；
5. **降级不崩**：``openpyxl`` 缺失 → 打印安装提示 + 只导 CSV + exit 0（不抛异常）。
"""

import csv
import io
import json
import sys
from pathlib import Path

import pytest

from labelcheck.report import (
    DETAIL_CSV, EVIDENCE_JSON, REPORT_MD, REPORT_XLSX, SUMMARY_CSV,
    build_report, render_evidence, render_markdown, write_report,
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


def _scan(cases, data_dir, **kwargs):
    return scan_target(cases, data_dir, **kwargs)


# ------------------------------------------------------------------ 格式齐备
def test_build_report_produces_required_files(cases, data_dir):
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    bundle = build_report(_scan(cases, data_dir), generated_at="2026-01-01T00:00:00")
    for name in (REPORT_MD, SUMMARY_CSV, DETAIL_CSV, EVIDENCE_JSON):
        assert name in bundle.files, "缺少产物：{0}".format(name)
    assert bundle.files[REPORT_MD]
    assert bundle.files[SUMMARY_CSV]


def test_write_report_writes_files_with_lf(cases, data_dir, tmp_path):
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    out = tmp_path / "out"
    bundle, written = write_report(_scan(cases, data_dir), out,
                                   generated_at="2026-01-01T00:00:00")
    assert (out / REPORT_MD).is_file()
    assert (out / SUMMARY_CSV).is_file()
    assert (out / DETAIL_CSV).is_file()
    assert (out / EVIDENCE_JSON).is_file()
    for path in (out / REPORT_MD, out / SUMMARY_CSV, out / DETAIL_CSV, out / EVIDENCE_JSON):
        assert b"\r" not in path.read_bytes(), "{0} 出现 CR".format(path.name)


# ------------------------------------------------------------------ 报告骨架
def test_markdown_has_mandatory_sections(cases, data_dir):
    _write_card(cases / "a.json", implicit={})
    text = render_markdown(_scan(cases, data_dir), generated_at="2026-01-01T00:00:00")
    assert "AI 生成合成内容标识合规核查报告" in text
    assert "2026-01-01T00:00:00" in text, "报告头须含调用方传入的生成时间"
    assert "规则库坐标" in text
    assert "免责声明" in text, "免责声明为强制段，不得省略"
    assert "核查范围" in text
    assert "依据清单" in text
    assert "逐件逐字段结果" in text
    assert "违规清单" in text
    assert "结论与建议" in text


def test_markdown_records_scenario_observed_and_parse_degradation(cases):
    """M2 口径必须进报告：场景 / 未观测作用域 / 解析降级原因（否则解析件被误读成显式合规）。

    用**仓库随附数据目录**（含 ``parse_profile.payload_wrapper``）——解析通路需要
    载荷画像才能识别 AIGC 载荷，"无载荷"与"无画像"是两种不同降级，此处要测前者。
    """
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from gen_parse import aigc_json, png_bytes

    # 一个解析件（显式未观测） + 一个 metadata 剥离的解析件（降级 no_aigc_payload）
    (cases / "img.png").write_bytes(
        png_bytes([("tEXt", "XML:com.adobe.xmp", aigc_json())]))
    (cases / "stripped.png").write_bytes(
        png_bytes([("tEXt", "Comment", "no aigc here")]))

    text = render_markdown(_scan(cases, ROOT / "data"), generated_at="2026-01-01T00:00:00")
    assert "适用场景" in text, "报告须写明适用场景（M2 口径）"
    assert "未观测作用域" in text, "报告须写明未观测作用域（解析件显式恒未观测）"
    assert "解析降级件" in text, "报告须写明解析降级件与原因码"
    assert "no_aigc_payload" in text
    # 逐件明细也要带 M2 口径（否则解析件会被误读成"显式合规"）
    assert "逐件可观测性" in text, "报告须有逐件可观测性表"
    assert "否（相关判定为 unknown）" in text, "逐件明细须标出未观测作用域"


def test_per_item_detail_carries_scenario_and_reasons(cases, data_dir):
    """逐件明细表须含 来源/场景/显式观测/隐式观测/解析降级原因 五列。"""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from gen_parse import aigc_json, png_bytes
    (cases / "img.png").write_bytes(
        png_bytes([("tEXt", "XML:com.adobe.xmp", aigc_json())]))
    text = render_markdown(_scan(cases, data_dir), generated_at="")
    assert "来源" in text and "场景" in text and "显式已观测" in text
    assert "隐式已观测" in text and "解析降级原因" in text


def test_markdown_lists_violations_and_failed_items(cases, data_dir):
    _write_card(cases / "bad.json", card_id="BAD", implicit={})
    (cases / "broken.json").write_text("{not json", encoding="utf-8")
    text = render_markdown(_scan(cases, data_dir), generated_at="")
    assert "BAD" in text
    assert "content_property" in text
    assert "失败件清单" in text
    assert "scan_error" in text


def test_summary_csv_has_one_row_per_item(cases, data_dir):
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    _write_card(cases / "b.json", card_id="B", implicit={})
    text = build_report(_scan(cases, data_dir)).files[SUMMARY_CSV]
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][0] == "card_id"
    assert len(rows) == 3, "表头 + 2 件"
    ids = sorted(row[0] for row in rows[1:])
    assert ids == ["A", "B"]


def test_detail_csv_has_one_row_per_finding(cases, data_dir):
    _write_card(cases / "a.json", card_id="A", implicit={})
    text = build_report(_scan(cases, data_dir)).files[DETAIL_CSV]
    rows = list(csv.reader(io.StringIO(text)))
    assert "scope" in rows[0] and "target" in rows[0] and "code" in rows[0]
    assert any(row[4] == "content_property" for row in rows[1:])
    assert any(row[3] == "implicit" for row in rows[1:])


# ------------------------------------------------------------------ 证据链（FR-9）
def test_evidence_contains_content_fingerprints(cases, data_dir):
    _write_card(cases / "a.json", card_id="A", content_sha256="c" * 64,
                implicit={"content.property": "AI"})
    bundle = build_report(_scan(cases, data_dir), generated_at="2026-01-01T00:00:00")
    evidence = json.loads(bundle.files[EVIDENCE_JSON])
    assert evidence["items"][0]["content_sha256"] == "c" * 64
    assert evidence["ruleset_coordinate"]
    assert evidence["generated_at"] == "2026-01-01T00:00:00"
    assert evidence["disclaimer"]


def test_evidence_contains_report_sha256(cases, data_dir):
    """证据链核心：``evidence.json`` 里的 ``report_sha256`` == report.md 的 sha256。"""
    from labelcheck.jsonio import sha256_text
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    bundle = build_report(_scan(cases, data_dir), generated_at="2026-01-01T00:00:00")
    evidence = json.loads(bundle.files[EVIDENCE_JSON])
    assert evidence["report_sha256"] == sha256_text(bundle.files[REPORT_MD])
    assert evidence["artifacts"][REPORT_MD] == evidence["report_sha256"]


def test_tampered_report_is_detectable(cases, data_dir):
    """报告被改动 → 与证据里的 sha256 不符（对照复现）。"""
    from labelcheck.jsonio import sha256_text
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    bundle = build_report(_scan(cases, data_dir), generated_at="2026-01-01T00:00:00")
    evidence = json.loads(bundle.files[EVIDENCE_JSON])
    tampered = bundle.files[REPORT_MD] + "\n（被人改过一行）\n"
    assert sha256_text(tampered) != evidence["report_sha256"]


# ------------------------------------------------------------------ 确定性（NFR-3）
def test_report_export_is_byte_identical_across_runs(cases, data_dir):
    """相同输入 + 相同 generated_at → 两次导出逐字节一致（含 XLSX）。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    first = build_report(_scan(cases, data_dir), generated_at="2026-01-01T00:00:00")
    second = build_report(_scan(cases, data_dir), generated_at="2026-01-01T00:00:00")
    for name in sorted(first.files):
        assert first.files[name] == second.files[name], "产物不一致：{0}".format(name)


def test_xlsx_is_deterministic_even_without_timestamp(cases, data_dir):
    """openpyxl 默认把文档属性/zip 条目写成当前时刻——必须被钉死，否则产物不可复现。"""
    openpyxl = pytest.importorskip("openpyxl", reason="需要 openpyxl 才能测 XLSX 确定性")
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    scan = _scan(cases, data_dir)
    from labelcheck.report import render_xlsx_bytes
    first = render_xlsx_bytes(scan, generated_at="")
    second = render_xlsx_bytes(scan, generated_at="")
    assert first == second, "XLSX 含未钉死的时间戳（产物不可复现）"


def test_report_without_generated_at_is_still_reproducible(cases, data_dir):
    """generated_at 为空字符串时同样逐字节一致（默认口径）。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    first = build_report(_scan(cases, data_dir))
    second = build_report(_scan(cases, data_dir))
    assert first.files[REPORT_MD] == second.files[REPORT_MD]
    assert first.files[EVIDENCE_JSON] == second.files[EVIDENCE_JSON]


# ------------------------------------------------------------------ XLSX 降级（plan/04 §八.2）
def test_xlsx_degrades_to_csv_when_openpyxl_missing(cases, data_dir, monkeypatch, capsys):
    """openpyxl 缺失 → 只导 CSV + 提示 + 不抛异常（exit 0 语义）。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    import labelcheck.report as report_mod

    def boom(*args, **kwargs):
        raise ImportError("No module named 'openpyxl'")

    monkeypatch.setattr(report_mod, "render_xlsx_bytes", boom)
    bundle = report_mod.build_report(_scan(cases, data_dir))
    assert REPORT_XLSX not in bundle.files
    assert bundle.xlsx_written is False
    assert "openpyxl" in bundle.xlsx_hint
    assert SUMMARY_CSV in bundle.files and DETAIL_CSV in bundle.files
    assert bundle.files[REPORT_MD]  # 报告仍产出


def test_xlsx_hint_is_frozen_aware(cases, data_dir, monkeypatch):
    """冻结态（发行 exe）下提示不得叫用户 `pip install`——冻结态装不了依赖。

    源码态提示给安装命令；冻结态提示改为"本发行包未内嵌 XLSX 导出"。
    """
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    import labelcheck.report as report_mod
    import labelcheck.paths as paths_mod

    def boom(*args, **kwargs):
        raise ImportError("No module named 'openpyxl'")

    monkeypatch.setattr(report_mod, "render_xlsx_bytes", boom)

    monkeypatch.setattr(paths_mod, "is_frozen", lambda: True)
    frozen = report_mod.build_report(_scan(cases, data_dir))
    assert "pip install" not in frozen.xlsx_hint, "冻结态不应提示 pip install"
    assert "发行包" in frozen.xlsx_hint

    monkeypatch.setattr(paths_mod, "is_frozen", lambda: False)
    source = report_mod.build_report(_scan(cases, data_dir))
    assert "pip install" in source.xlsx_hint


def test_report_includes_diff_section_when_given(cases, data_dir):
    """传入对账结果时，报告含"两轮对账"段。"""
    from labelcheck.scan import diff_scans
    _write_card(cases / "a.json", card_id="A", implicit={})
    previous = _scan(cases, data_dir)
    _write_card(cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    current = _scan(cases, data_dir)
    diff = diff_scans(previous, current)

    bundle = build_report(current, generated_at="2026-01-01T00:00:00", diff=diff)
    text = bundle.files[REPORT_MD]
    assert "两轮对账" in text
    assert "已修复" in text
    evidence = json.loads(bundle.files[EVIDENCE_JSON])
    assert evidence["diff"]["summary"]["fixed"] == 1