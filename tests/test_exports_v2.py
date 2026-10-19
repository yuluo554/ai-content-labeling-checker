# -*- coding: utf-8 -*-
"""v0.2.0 追加能力的测试：SARIF 导出 / 单文件 HTML 报告 / ``rules`` 只读子命令。

**为什么单列一个文件**：这三项是"只读导出与查询"，与既有判定/分级逻辑**无耦合**。
独立文件使"新增能力"与"既有契约"的测试边界清楚：本文件任一条失败都指向新能力，
不会让人误以为规则库或引擎口径变了。

锁死四件事：

1. **SARIF 结构合法**：2.1.0、``runs[0].results`` 与报告里的 fail/unknown 一一对应，
   ``level`` 由既有 ``severity`` 固定映射，``skipped`` 不出现（与报告口径一致）；
2. **HTML 单文件自足**：零外链（``http(s)://`` 出现 0 次）、强制免责声明在、表格行数
   与件数一致、用户输入被转义（XSS 面）；
3. **两者都不改默认报告包**：``build_report`` 的五产物与 ``evidence.json`` 指纹不变；
4. **``rules`` 只读**：JSON/human 两路输出、``--scope``/``--status``/``--mapping`` 过滤
   正确、退出码 0、不写任何文件。
"""

import json
from pathlib import Path

import pytest

from labelcheck.cli.main import main
from labelcheck.report import (
    REPORT_MD, SARIF_VERSION, build_report, render_html, render_sarif,
)
from labelcheck.scan import scan_target

from _support import build_data_dir, make_card, make_mapping_field, make_rule


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cases(tmp_path):
    path = tmp_path / "cases"
    path.mkdir()
    return path


@pytest.fixture
def data_dir(tmp_path):
    """一份合规件 + 一件缺字段（fail）+ 一件缺值不可核验（unknown）。"""
    return build_data_dir(
        tmp_path / "data",
        {"doc": {"version": "2025-09-01", "status": "verified",
                 "rules": [
                     make_rule("r-presence", scope="implicit",
                               target="content_property", check_type="presence",
                               severity="critical", status="verified"),
                     make_rule("r-pattern", scope="implicit",
                               target="content_producer", check_type="pattern",
                               params={"regex": "^[A-Z]{3}$"},
                               severity="minor", status="verified"),
                 ]}},
        mapping_fields=[
            make_mapping_field("content_property", ["content.property"], status="verified"),
            make_mapping_field("content_producer", ["service.provider"], status="verified"),
        ],
    )


def _write_card(path, **overrides):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(make_card(**overrides), ensure_ascii=False), encoding="utf-8")
    return path


def _three_cards(cases):
    """合规件 / fail（缺字段）/ unknown（字段存在但由于其它规则...）各一。"""
    _write_card(cases / "ok.json", card_id="OK",
                implicit={"content.property": "1", "service.provider": "ABC"})
    _write_card(cases / "bad.json", card_id="BAD", implicit={})
    _write_card(cases / "review.json", card_id="REV",
                implicit={"content.property": "1"})
    return cases


# ------------------------------------------------------------------ SARIF
def test_sarif_is_version_2_1_0_and_parses(cases, data_dir):
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    payload = json.loads(render_sarif(scan, generated_at="2026-01-01T00:00:00"))
    assert payload["version"] == SARIF_VERSION == "2.1.0"
    assert payload["$schema"]
    assert len(payload["runs"]) == 1
    run = payload["runs"][0]
    assert run["tool"]["driver"]["name"] == "labelcheck"
    assert run["invocations"][0]["startTimeUtc"] == "2026-01-01T00:00:00"
    assert run["properties"]["disclaimer"], "免责声明必须随 SARIF 固化"


def test_sarif_results_mirror_fail_and_unknown_but_not_skipped(cases, data_dir):
    """SARIF 结果集 = 报告里的 fail ∪ unknown；``skipped`` 不导出。

    ``unknown`` 必须保留（``level=note`` + ``properties.status=unknown``）——抹掉它
    就是"把没检查说成没问题"（假合规）。
    """
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    payload = json.loads(render_sarif(scan))
    results = payload["runs"][0]["results"]

    expected = []
    for item in scan.checked:
        for finding in item.report.all_findings:
            if finding.status in ("fail", "unknown"):
                expected.append((item.card_id, finding.target, finding.status))
    got = [(r["properties"]["card_id"], r["properties"]["target"],
            r["properties"]["status"]) for r in results]
    assert sorted(got) == sorted(expected)

    statuses = set(r["properties"]["status"] for r in results)
    assert "fail" in statuses, "用例未覆盖 fail 分支"
    assert "unknown" in statuses, "用例未覆盖 unknown 分支"
    assert "skipped" not in statuses, "skipped 不适用，不应出现在 SARIF 里"


def test_sarif_level_maps_from_existing_severity(cases, data_dir):
    """``level`` 只能是既有 severity 的固定映射（不新增判定语义）。"""
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    payload = json.loads(render_sarif(scan))
    mapping = {"critical": "error", "major": "warning", "minor": "note"}
    for result in payload["runs"][0]["results"]:
        status = result["properties"]["status"]
        severity = result["properties"]["severity"]
        if status == "fail":
            assert result["level"] == mapping[severity], (
                "fail 的 level 必须由 severity 映射：{0} → {1}".format(
                    severity, result["level"]))
        else:
            assert result["level"] == "note", "unknown 一律 note"


def test_sarif_rules_carry_clause_and_are_deduplicated(cases, data_dir):
    """``ruleId`` 取原因码，规则条目带条款；同一 ruleId 只登记一次。"""
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    payload = json.loads(render_sarif(scan))
    rules = payload["runs"][0]["tool"]["driver"]["rules"]
    ids = [rule["id"] for rule in rules]
    assert len(ids) == len(set(ids)), "规则条目重复（SARIF 要求 rules 按 id 唯一）"
    for rule in rules:
        assert rule["properties"]["clause"], "规则条目必须挂条款号"


def test_sarif_is_deterministic(cases, data_dir):
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    assert render_sarif(scan, generated_at="2026-01-01T00:00:00") == \
        render_sarif(scan, generated_at="2026-01-01T00:00:00")


def test_sarif_records_failed_items_as_error(cases, data_dir):
    (cases / "broken.json").write_text("{not json", encoding="utf-8")
    manifest = cases / "list.lst"
    manifest.write_text("broken.json\n", encoding="utf-8")
    scan = scan_target(manifest, data_dir)
    payload = json.loads(render_sarif(scan))
    results = payload["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["ruleId"] == "scan_error"
    assert results[0]["level"] == "error"
    assert results[0]["properties"]["status"] == "failed"


def test_sarif_uri_uses_posix_separators(cases, data_dir):
    """``artifactLocation.uri`` 统一 POSIX（跨平台导出字节一致）。"""
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    payload = json.loads(render_sarif(scan))
    for result in payload["runs"][0]["results"]:
        uri = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        assert "\\" not in uri, "uri 出现反斜杠：{0}".format(uri)


# ------------------------------------------------------------------ HTML
def test_html_is_self_contained_and_escapes_input(cases, data_dir):
    """单文件自足（零外链）+ 用户输入转义（card_id 可含尖括号/引号）。

    Windows 文件名不允许 ``<``/``>``，故用文件名里的 ``&`` 与 ``card_id`` 里的
    标签串共同覆盖转义面。
    """
    _write_card(cases / "a&b.json", card_id="<script>alert(1)</script>",
                implicit={})
    scan = scan_target(cases, data_dir)
    html = render_html(scan, generated_at="2026-01-01T00:00:00")

    assert html.startswith("<!DOCTYPE html>")
    assert "<script" not in html.lower(), "HTML 报告不得含脚本（零 JS 承诺）"
    assert "http://" not in html and "https://" not in html, (
        "单文件报告不得引用外部资源（打开即联网违背'零上传'）")
    assert "&lt;script&gt;" in html, "card_id 未被转义（XSS 面）"
    assert "a&amp;b.json" in html, "件路径未被转义"


def test_html_keeps_mandatory_disclaimer_and_all_sections(cases, data_dir):
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    html = render_html(scan, generated_at="2026-01-01T00:00:00")
    assert "免责声明" in html
    assert "不提供任何标识规避功能" in html
    for section in ("核查范围", "依据清单", "逐件结果", "违规清单", "结论与建议"):
        assert section in html, "缺少段落：{0}".format(section)


def test_html_row_counts_match_scan(cases, data_dir):
    """逐件表行数 = 件数；逐字段表行数 = 全部 Finding 数。"""
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    html = render_html(scan)

    def rows_between(start_marker, end_marker):
        section = html.split(start_marker, 1)[1].split(end_marker, 1)[0]
        return section.count("<tr>")

    items_rows = rows_between("3.1 逐件可观测性", "3.2 逐要素/逐字段判定")
    findings_rows = rows_between("3.2 逐要素/逐字段判定", "<h2>四、违规清单")
    findings = sum(len(item.report.all_findings) for item in scan.checked)
    # 每张表各含 1 行表头
    assert items_rows == 1 + len(scan.items)
    assert findings_rows == 1 + findings


def test_html_is_deterministic(cases, data_dir):
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    assert render_html(scan, generated_at="2026-01-01T00:00:00") == \
        render_html(scan, generated_at="2026-01-01T00:00:00")


def test_html_with_diff_renders_reconciliation(cases, data_dir):
    from labelcheck.scan import diff_scans

    _write_card(cases / "a.json", card_id="A", implicit={})
    previous = scan_target(cases, data_dir)
    _write_card(cases / "a.json", card_id="A",
                implicit={"content.property": "1", "service.provider": "ABC"})
    current = scan_target(cases, data_dir)
    diff = diff_scans(previous, current)
    html = render_html(current, diff=diff)
    assert "两轮对账" in html
    assert "已修复" in html


# ------------------------------------------------------------------ 默认报告包不变
def test_new_exports_do_not_change_default_bundle(cases, data_dir):
    """新增导出是**可选旁路**：默认五产物与证据链指纹必须一字不差。"""
    _three_cards(cases)
    scan = scan_target(cases, data_dir)
    bundle = build_report(scan, generated_at="2026-01-01T00:00:00")
    assert sorted(bundle.files) == sorted([
        "report.md", "summary.csv", "detail.csv", "report.xlsx", "evidence.json",
    ]), "默认报告包不应因新格式而增减"
    assert "sarif" not in bundle.files["evidence.json"].lower()
    assert "html" not in bundle.files["evidence.json"].lower()


# ------------------------------------------------------------------ rules 子命令
def test_rules_json_lists_all_entries_including_pending(data_dir, capsys):
    """缺省同时列 verified 与 pending——"哪条还没核对"是用户要的信息。"""
    code = main(["--data-dir", str(data_dir), "rules", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["verified_rule_count"] == 2
    assert payload["pending_rule_count"] == 0
    assert len(payload["rules"]) == 2
    assert all(rule["effective"] for rule in payload["rules"])

    # 加一条 pending 规则后，缺省应把它也列出来
    data_dir2 = build_data_dir(
        Path(str(data_dir)) / "v2",
        {"doc": {"version": "2025-09-01", "status": "verified",
                 "rules": [
                     make_rule("r-verified", scope="implicit", target="content_property",
                               check_type="presence", status="verified"),
                     make_rule("r-pending", scope="explicit",
                               target="text_explicit_notice", check_type="presence",
                               status="pending"),
                 ]}},
        mapping_fields=[make_mapping_field("content_property", ["content.property"],
                                           status="verified")],
    )
    code = main(["--data-dir", str(data_dir2), "rules", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len(payload["rules"]) == 2
    assert payload["verified_rule_count"] == 1
    assert payload["pending_rule_count"] == 1


def test_rules_filters_by_scope_and_status(data_dir, capsys):
    base = Path(str(data_dir)) / "filtered"
    data_dir2 = build_data_dir(
        base,
        {"doc": {"version": "2025-09-01", "status": "verified",
                 "rules": [
                     make_rule("r-imp", scope="implicit", target="content_property",
                               check_type="presence", status="verified"),
                     make_rule("r-exp", scope="explicit",
                               target="text_explicit_notice", check_type="presence",
                               status="pending"),
                 ]}},
        mapping_fields=[make_mapping_field("content_property", ["content.property"],
                                           status="verified")],
    )
    code = main(["--data-dir", str(data_dir2), "rules", "--scope", "explicit", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [r["rule_id"] for r in payload["rules"]] == ["r-exp"]

    code = main(["--data-dir", str(data_dir2), "rules", "--status", "verified", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [r["rule_id"] for r in payload["rules"]] == ["r-imp"]


def test_rules_mapping_flag_includes_field_table(data_dir, capsys):
    code = main(["--data-dir", str(data_dir), "rules", "--mapping", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["mapping"]["verified_field_count"] == 2
    names = [f["national_field"] for f in payload["mapping"]["fields"]]
    assert "content_property" in names


def test_rules_human_output_mentions_coordinate_and_entries(data_dir, capsys):
    code = main(["--data-dir", str(data_dir), "rules"])
    out = capsys.readouterr().out
    assert code == 0
    assert "规则库坐标" in out
    assert "r-presence" in out
    assert "r-pattern" in out


def test_rules_is_registered_in_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "rules" in capsys.readouterr().out


def test_rules_subcommand_does_not_write_anything(data_dir, tmp_path, capsys):
    """只读承诺：跑完前后数据目录的文件列表与内容都必须不变。"""
    before = {p: p.read_bytes() for p in sorted(Path(str(data_dir)).rglob("*")) if p.is_file()}
    main(["--data-dir", str(data_dir), "rules", "--mapping", "--json"])
    capsys.readouterr()
    after = {p: p.read_bytes() for p in sorted(Path(str(data_dir)).rglob("*")) if p.is_file()}
    assert before == after, "rules 子命令改动了数据目录（应为纯只读）"


# ------------------------------------------------------------------ CLI 接线
def test_scan_sarif_and_html_write_to_explicit_paths(cases, data_dir, tmp_path, capsys):
    _three_cards(cases)
    sarif = tmp_path / "out.sarif"
    html = tmp_path / "out.html"
    code = main(["--data-dir", str(data_dir), "scan", str(cases),
                 "--sarif", str(sarif), "--html", str(html), "--quiet"])
    captured = capsys.readouterr()
    # 有不合规件 → scan 退出码 1（**检出不合规**，不是错误；退出码语义未改）
    assert code == 1
    assert sarif.is_file() and html.is_file()
    assert "SARIF 已导出" in captured.err
    assert "HTML 报告已导出" in captured.err
    assert json.loads(sarif.read_text(encoding="utf-8"))["version"] == "2.1.0"

    # 默认报告包未被创建（未给 --out）
    assert not (tmp_path / "report.md").exists()
