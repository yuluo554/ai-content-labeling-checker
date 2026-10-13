"""GUI 页签测试（offscreen）：**只渲染引擎结果**的端到端冒烟。

无 PySide6 的环境用 ``pytest.importorskip`` 声明式跳过（CI 的 ``.[dev]`` 通路即此情形）；
有 GUI 的环境在 ``QT_QPA_PLATFORM=offscreen`` 下驱动真实控件——不进入事件循环，
直接调页签的普通方法（``check_path`` / ``scan`` / ``run`` / ``refresh``），断言
控件里渲染出的行数与引擎对象一致。

**为什么必须 offscreen 驱动真控件**：服务层测试只证明"数据对"，证明不了"控件真的把
数据画出来了"（控件连线写错、列数不匹配、渲染时抛异常都只在构造后才暴露）。
"""

import json
import os
from pathlib import Path

import pytest

# 必须在导入 PySide6 之前设置（否则无显示环境会直接崩）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="GUI 测试需要 PySide6（gui extra）")

from PySide6.QtWidgets import QApplication  # noqa: E402

from labelcheck.gui import format as fmt  # noqa: E402
from labelcheck.gui.main_window import MainWindow  # noqa: E402
from labelcheck.gui.tabs import (  # noqa: E402
    AboutTab, BatchScanTab, BenchmarkTab, DiffTab, RulesTab, SingleCheckTab, TAB_CLASSES,
)

from _support import build_data_dir, make_card, make_mapping_field, make_rule  # noqa: E402


@pytest.fixture(scope="module")
def app():
    """整个模块共用一个 QApplication（Qt 不允许重复构造）。"""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def verified_data(tmp_path):
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


# ------------------------------------------------------------------ 主窗口装配
def test_main_window_builds_six_tabs(app, repo_root):
    window = MainWindow(data_dir=repo_root / "data")
    titles = [tab.TITLE for tab in window.tab_objects]
    assert titles == [cls.TITLE for cls in TAB_CLASSES]
    assert window.tabs.count() == 6
    assert "两轮对账" in titles, "两轮对账须为独立页签（plan/HANDOFF-M5 §三.1）"
    assert str(repo_root / "data") in window.status_label.text()


def test_main_window_without_data_dir_shows_hint(app):
    window = MainWindow(data_dir=None)
    assert "未定位数据目录" in window.status_label.text()


def test_set_data_dir_propagates_to_tabs(app, tmp_path, verified_data):
    window = MainWindow(data_dir=None)
    window.set_data_dir(verified_data)
    for tab in window.tab_objects:
        assert tab.data_dir == Path(verified_data)


# ------------------------------------------------------------------ 单件核验页签
def test_single_check_tab_renders_report(app, tmp_path, verified_data):
    tab = SingleCheckTab(verified_data)
    path = _write_card(tmp_path / "cases" / "ok.json", implicit={"content.property": "AI"})

    result = tab.check_path(str(path))
    assert result is not None
    assert result.grade == "compliant"
    # 概要表 + 判定表都被真实填充
    assert tab.summary_table.rowCount() == len(fmt.report_summary(result.report))
    assert tab.findings_table.rowCount() == len(result.report.all_findings)
    assert "compliant" in tab.text_view.toPlainText()


def test_single_check_tab_renders_violation(app, tmp_path, verified_data):
    tab = SingleCheckTab(verified_data)
    path = _write_card(tmp_path / "cases" / "bad.json", implicit={})
    result = tab.check_path(str(path))
    assert result.has_violation is True
    assert tab.findings_table.rowCount() >= 1


def test_single_check_tab_error_is_shown_not_raised(app, verified_data, tmp_path, monkeypatch):
    """引擎抛可预期错误时，页签应弹提示并返回 None（不把异常抛穿到事件循环）。"""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    tab = SingleCheckTab(verified_data)
    result = tab.check_path(str(tmp_path / "nope.json"))
    assert result is None
    assert "核验失败" in tab.text_view.toPlainText()


def test_single_check_tab_without_data_dir_returns_none(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    tab = SingleCheckTab(None)
    path = _write_card(tmp_path / "cases" / "ok.json", implicit={"content.property": "AI"})
    assert tab.check_path(str(path)) is None


# ------------------------------------------------------------------ 批量扫描页签
def test_batch_scan_tab_renders_items_and_enables_export(app, tmp_path, verified_data):
    tab = BatchScanTab(verified_data)
    cases = tmp_path / "cases"
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    _write_card(cases / "b.json", implicit={})

    batch = tab.scan(str(cases))
    assert batch is not None
    assert tab.items_table.rowCount() == len(batch.result.items)
    assert tab.summary_table.rowCount() == len(fmt.scan_summary(batch.result))
    assert tab.diff_table.rowCount() == 0, "无 baseline 时对账表为空"
    assert tab.export_button.isEnabled() is True


def test_batch_scan_tab_renders_diff_when_baseline_given(app, tmp_path, verified_data):
    tab = BatchScanTab(verified_data)
    cases = tmp_path / "cases"
    _write_card(cases / "a.json", implicit={})
    first = tab.scan(str(cases))

    baseline_path = tmp_path / "round1.json"
    baseline_path.write_text(
        json.dumps(first.result.to_dict(), ensure_ascii=False), encoding="utf-8")

    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    tab.baseline_edit.setText(str(baseline_path))
    second = tab.scan(str(cases))
    assert second.diff is not None
    assert tab.diff_table.rowCount() == len(fmt.diff_rows(second.diff))
    assert "已修复" in tab.text_view.toPlainText()


def test_batch_scan_tab_export_writes_files(app, tmp_path, verified_data, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    tab = BatchScanTab(verified_data)
    cases = tmp_path / "cases"
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    tab.scan(str(cases))

    out = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(out)))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    tab._on_export()
    assert (out / "report.md").is_file()


# ------------------------------------------------------------------ 两轮对账页签
def test_diff_tab_renders_sets_from_two_result_files(app, tmp_path, verified_data):
    """独立对账页签：喂两份 ScanResult JSON → 渲染四类集合 + 辅助集合。"""
    cases = tmp_path / "cases"
    _write_card(cases / "a.json", implicit={})

    scan_tab = BatchScanTab(verified_data)
    first = scan_tab.scan(str(cases))
    round1 = tmp_path / "round1.json"
    round1.write_text(json.dumps(first.result.to_dict(), ensure_ascii=False), encoding="utf-8")

    # 修复 → 第二轮无违规
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    second = scan_tab.scan(str(cases))
    round2 = tmp_path / "round2.json"
    round2.write_text(json.dumps(second.result.to_dict(), ensure_ascii=False), encoding="utf-8")

    tab = DiffTab(verified_data)
    result = tab.diff(str(round1), str(round2))
    assert result is not None
    assert result.summary["fixed"] == 1
    assert tab.diff_table.rowCount() == len(fmt.diff_rows(result))
    assert tab.summary_table.rowCount() == len(fmt.diff_summary(result))
    assert "已修复" in tab.text_view.toPlainText()


def test_diff_tab_bad_input_shows_error_not_raises(app, tmp_path, verified_data, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"nope": 1}), encoding="utf-8")
    tab = DiffTab(verified_data)
    assert tab.diff(str(bad), str(bad)) is None
    assert "对账失败" in tab.text_view.toPlainText()


# ------------------------------------------------------------------ 基准指标页签
def test_benchmark_tab_runs_all_suites(app, repo_root):
    tab = BenchmarkTab(repo_root / "data")
    report = tab.run(None)
    assert report.passed is True
    assert tab.metrics_table.rowCount() == len(fmt.bench_rows(report))
    assert tab.verdict_label.text() == "全部达标"
    assert "fields" in tab.text_view.toPlainText()


def test_benchmark_tab_subset_selection(app, repo_root):
    tab = BenchmarkTab(repo_root / "data")
    tab.only_edit.setText("diff")
    report = tab.run(tab._parse_only())
    assert [s.name for s in report.suites] == ["diff"]


# ------------------------------------------------------------------ 规则库页签
def test_rules_tab_renders_documents_and_rules(app, repo_root):
    tab = RulesTab(repo_root / "data")
    overview = tab.refresh()
    assert overview.ruleset.verified_rule_count > 0
    assert tab.docs_table.rowCount() == len(fmt.document_rows(overview.ruleset))
    assert tab.rules_table.rowCount() == len(fmt.rule_rows(overview.ruleset))
    assert tab.mapping_table.rowCount() == len(fmt.mapping_rows(overview.mapping_table))
    assert overview.ruleset.coordinate in tab.coordinate_label.text()


# ------------------------------------------------------------------ 关于页签
def test_about_tab_contains_disclaimer_and_positioning(app):
    tab = AboutTab()
    text = tab.browser.toPlainText()
    assert "免责声明" in text
    assert "合规核查防线" in text
