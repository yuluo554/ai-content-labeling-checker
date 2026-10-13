# -*- coding: utf-8 -*-
"""GUI 页签（PySide6）：**只渲染引擎结果，零判定逻辑**（plan/03 §一 分层图）。

六个页签对应六条既有能力，每个页签的"干活"步骤都只是调 :mod:`labelcheck.gui.services`
（而后者只调引擎）：

============  ==========================================  ==========================
页签           展示内容                                     调用的引擎入口
============  ==========================================  ==========================
单件核验       ``CheckReport``（概要 + 逐条判定）            ``engine.check_file``
批量扫描        ``ScanResult``（+ 可选两轮对账）              ``scan.scan_target``（+ ``scan.diff_scans``）
两轮对账        ``DiffResult``（两份结果 JSON 对账）          ``scan.diff_scans``
基准指标       ``BenchReport``（三类指标 + 达标线）           ``benchmark.run_benchmark``
规则库与依据    规则库坐标 + 依据清单 + 规则/映射条目          ``rules.effective_ruleset`` / ``mapping.load_mapping_table``
关于           工具定位与免责声明                             ``labelcheck.POSITIONING`` / ``DISCLAIMER``
============  ==========================================  ==========================

**可测性**：每个页签把"调引擎 + 刷新控件"暴露为普通方法（``check_path`` / ``scan`` /
``diff`` / ``run`` / ``refresh``），返回引擎对象——offscreen 下无需真实交互即可断言（见
``tests/test_gui_tabs.py``）。**判定/分级/分派逻辑一律不在此层**，全部取自引擎返回值。
"""

from pathlib import Path

from .. import DISCLAIMER, POSITIONING, __version__
from ..benchmark import BENCH_NAMES, BENCH_TITLES
from . import format as fmt
from . import services

#: 无数据目录时的提示（界面统一文案）
NO_DATA_DIR_HINT = "未定位到数据目录：请在上方选择仓库 data/ 目录（或设置环境变量 LABELCHECK_DATA_DIR）。"


def _qt():
    """惰性取 Qt 符号（避免模块顶层 import PySide6，便于无 GUI 环境导入本模块）。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QAbstractItemView, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
        QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
        QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
    )
    return locals()


class _TabBase(object):
    """页签共用：数据目录注入 + 状态提示 + 表格构造。"""

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else None

    # ------------------------------------------------------------------ 数据目录
    def set_data_dir(self, data_dir):
        """注入数据目录（由主窗口统一下发；``None`` = 未定位）。"""
        self.data_dir = Path(data_dir) if data_dir else None

    def _require_data_dir(self):
        """返回数据目录；未设置则抛 :class:`labelcheck.errors.EnvironmentError_`。"""
        if self.data_dir is None:
            from ..errors import EnvironmentError_

            raise EnvironmentError_(NO_DATA_DIR_HINT)
        return self.data_dir

    # ------------------------------------------------------------------ 表格
    @staticmethod
    def _make_table(columns):
        qt = _qt()
        table = qt["QTableWidget"](0, len(columns))
        table.setHorizontalHeaderLabels(list(columns))
        table.setEditTriggers(qt["QAbstractItemView"].NoEditTriggers)
        table.setSelectionBehavior(qt["QAbstractItemView"].SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(qt["QHeaderView"].Interactive)
        return table

    @staticmethod
    def _fill_table(table, rows):
        qt = _qt()
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                item = qt["QTableWidgetItem"](str(value))
                item.setToolTip(str(value))
                table.setItem(row_index, col_index, item)
        table.resizeColumnsToContents()

    @staticmethod
    def _kv_group(title, pairs=()):
        """``[(标签, 值)]`` → ``(只读键值表所在的分组框, 表控件)``（概要区）。

        返回表控件本身，便于刷新时直接 :meth:`_fill_table`（不靠 ``findChildren`` 反查）。
        """
        qt = _qt()
        group = qt["QGroupBox"](title)
        layout = qt["QVBoxLayout"](group)
        table = _TabBase._make_table(("项目", "值"))
        _TabBase._fill_table(table, pairs)
        layout.addWidget(table)
        return group, table


# ------------------------------------------------------------------ 单件核验
class SingleCheckTab(_TabBase):
    """单件核验页签：选文件 → ``engine.check_file`` → 概要 + 逐条判定。"""

    TITLE = "单件核验"

    def __init__(self, data_dir=None):
        _TabBase.__init__(self, data_dir)
        qt = _qt()
        self.widget = qt["QWidget"]()
        root = qt["QVBoxLayout"](self.widget)

        picker = qt["QHBoxLayout"]()
        picker.addWidget(qt["QLabel"]("输入文件（标识卡 JSON 或 PNG/JPEG/MP4/M4A）："))
        self.path_edit = qt["QLineEdit"]()
        picker.addWidget(self.path_edit, 1)
        self.browse_button = qt["QPushButton"]("选择…")
        self.browse_button.clicked.connect(self._on_browse)
        picker.addWidget(self.browse_button)

        picker.addWidget(qt["QLabel"]("场景："))
        self.scenario_combo = qt["QComboBox"]()
        for label, value in services.scenario_options():
            self.scenario_combo.addItem(label, value)
        picker.addWidget(self.scenario_combo)

        self.check_button = qt["QPushButton"]("核验")
        self.check_button.clicked.connect(self._on_check)
        picker.addWidget(self.check_button)
        root.addLayout(picker)

        splitter = qt["QSplitter"]()
        self.summary_group, self.summary_table = self._kv_group("核验概要")
        splitter.addWidget(self.summary_group)
        findings_box = qt["QGroupBox"]("逐条判定")
        findings_layout = qt["QVBoxLayout"](findings_box)
        self.findings_table = self._make_table(fmt.FINDING_COLUMNS)
        findings_layout.addWidget(self.findings_table)
        splitter.addWidget(findings_box)
        root.addWidget(splitter, 1)

        self.text_view = qt["QPlainTextEdit"]()
        self.text_view.setReadOnly(True)
        self.text_view.setPlaceholderText("核验结论文本（可复制）")
        root.addWidget(self.text_view)

    # ------------------------------------------------------------------ 行为
    def _on_browse(self):
        qt = _qt()
        path, _filter = qt["QFileDialog"].getOpenFileName(
            self.widget, "选择待核验文件", "",
            "可核验文件 (*.json *.png *.jpg *.jpeg *.mp4 *.m4a);;全部文件 (*)")
        if path:
            self.path_edit.setText(path)

    def _on_check(self):
        path = self.path_edit.text().strip()
        if path:
            self.check_path(path)

    def check_path(self, path):
        """核验给定路径并刷新界面；返回 :class:`~labelcheck.gui.services.SingleCheckResult`。

        引擎异常（文件不存在/非法输入）→ 弹提示并返回 ``None``（不崩、不臆造结论）。
        """
        try:
            result = services.check_single(
                path, self._require_data_dir(),
                scenario=self.scenario_combo.currentData())
        except Exception as exc:  # noqa: BLE001 - 界面须把任何可预期错误转成提示
            self._show_error(exc)
            return None
        self._render(result)
        return result

    def _render(self, result):
        self._fill_table(self.summary_table, fmt.report_summary(result.report))
        self._fill_table(self.findings_table, fmt.finding_rows(result.report))
        self.text_view.setPlainText(fmt.report_text(result))

    def _show_error(self, exc):
        qt = _qt()
        message = str(exc)
        self.text_view.setPlainText("核验失败：{0}".format(message))
        self._fill_table(self.findings_table, [])
        qt["QMessageBox"].warning(self.widget, "核验失败", message)


# ------------------------------------------------------------------ 批量扫描
class BatchScanTab(_TabBase):
    """批量扫描页签：选目录/清单 → ``scan.scan_target``（+ 可选对账）→ 导出报告。"""

    TITLE = "批量扫描"

    def __init__(self, data_dir=None):
        _TabBase.__init__(self, data_dir)
        qt = _qt()
        self.widget = qt["QWidget"]()
        root = qt["QVBoxLayout"](self.widget)

        target_row = qt["QHBoxLayout"]()
        target_row.addWidget(qt["QLabel"]("扫描目标（目录或清单文件）："))
        self.target_edit = qt["QLineEdit"]()
        target_row.addWidget(self.target_edit, 1)
        self.target_button = qt["QPushButton"]("选择目录…")
        self.target_button.clicked.connect(self._on_browse_target)
        target_row.addWidget(self.target_button)
        self.manifest_button = qt["QPushButton"]("选择清单…")
        self.manifest_button.clicked.connect(self._on_browse_manifest)
        target_row.addWidget(self.manifest_button)
        target_row.addWidget(qt["QLabel"]("场景："))
        self.scenario_combo = qt["QComboBox"]()
        for label, value in services.scenario_options():
            self.scenario_combo.addItem(label, value)
        target_row.addWidget(self.scenario_combo)
        root.addLayout(target_row)

        baseline_row = qt["QHBoxLayout"]()
        baseline_row.addWidget(qt["QLabel"]("上轮结果 JSON（可选，用于两轮对账）："))
        self.baseline_edit = qt["QLineEdit"]()
        baseline_row.addWidget(self.baseline_edit, 1)
        self.baseline_button = qt["QPushButton"]("选择…")
        self.baseline_button.clicked.connect(self._on_browse_baseline)
        baseline_row.addWidget(self.baseline_button)
        root.addLayout(baseline_row)

        action_row = qt["QHBoxLayout"]()
        self.scan_button = qt["QPushButton"]("开始扫描")
        self.scan_button.clicked.connect(self._on_scan)
        action_row.addWidget(self.scan_button)
        self.export_button = qt["QPushButton"]("导出报告…")
        self.export_button.clicked.connect(self._on_export)
        self.export_button.setEnabled(False)
        action_row.addWidget(self.export_button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        splitter = qt["QSplitter"]()
        self.summary_group, self.summary_table = self._kv_group("扫描概要")
        splitter.addWidget(self.summary_group)
        items_box = qt["QGroupBox"]("逐件结果")
        items_layout = qt["QVBoxLayout"](items_box)
        self.items_table = self._make_table(fmt.SCAN_ITEM_COLUMNS)
        items_layout.addWidget(self.items_table)
        splitter.addWidget(items_box)
        root.addWidget(splitter, 1)

        self.diff_group = qt["QGroupBox"]("两轮对账")
        diff_layout = qt["QVBoxLayout"](self.diff_group)
        self.diff_table = self._make_table(fmt.DIFF_COLUMNS)
        diff_layout.addWidget(self.diff_table)
        root.addWidget(self.diff_group)

        self.text_view = qt["QPlainTextEdit"]()
        self.text_view.setReadOnly(True)
        self.text_view.setPlaceholderText("扫描结论文本（可复制）")
        root.addWidget(self.text_view)

        self.batch = None

    # ------------------------------------------------------------------ 行为
    def _on_browse_target(self):
        qt = _qt()
        path = qt["QFileDialog"].getExistingDirectory(self.widget, "选择待扫描目录")
        if path:
            self.target_edit.setText(path)

    def _on_browse_manifest(self):
        qt = _qt()
        path, _filter = qt["QFileDialog"].getOpenFileName(
            self.widget, "选择清单文件", "", "清单 (*.lst *.list *.manifest *.txt);;全部文件 (*)")
        if path:
            self.target_edit.setText(path)

    def _on_browse_baseline(self):
        qt = _qt()
        path, _filter = qt["QFileDialog"].getOpenFileName(
            self.widget, "选择上轮 ScanResult JSON", "", "JSON (*.json);;全部文件 (*)")
        if path:
            self.baseline_edit.setText(path)

    def _on_scan(self):
        target = self.target_edit.text().strip()
        if target:
            self.scan(target)

    def _on_export(self):
        qt = _qt()
        if self.batch is None:
            return
        out_dir = qt["QFileDialog"].getExistingDirectory(self.widget, "选择报告导出目录")
        if not out_dir:
            return
        try:
            written = services.export_report(self.batch, out_dir)
        except Exception as exc:  # noqa: BLE001
            qt["QMessageBox"].warning(self.widget, "导出失败", str(exc))
            return
        qt["QMessageBox"].information(
            self.widget, "导出完成",
            "已导出 {0} 个文件：\n{1}".format(
                len(written), "\n".join(str(p) for p in written)))

    def scan(self, target):
        """扫描给定目标并刷新界面；返回 :class:`~labelcheck.gui.services.BatchScanResult`。"""
        try:
            baseline = None
            baseline_path = self.baseline_edit.text().strip()
            if baseline_path:
                baseline = services.load_baseline(baseline_path)
            batch = services.scan_batch(
                target, self._require_data_dir(),
                scenario=self.scenario_combo.currentData(), baseline=baseline)
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return None
        self._render(batch)
        return batch

    def _render(self, batch):
        self.batch = batch
        self._fill_table(self.summary_table, fmt.scan_summary(batch.result))
        self._fill_table(self.items_table, fmt.scan_item_rows(batch.result))
        self._fill_table(self.diff_table, fmt.diff_rows(batch.diff) if batch.diff else [])
        self.text_view.setPlainText(fmt.scan_text(batch))
        self.export_button.setEnabled(True)

    def _show_error(self, exc):
        qt = _qt()
        self.text_view.setPlainText("扫描失败：{0}".format(exc))
        qt["QMessageBox"].warning(self.widget, "扫描失败", str(exc))


# ------------------------------------------------------------------ 两轮对账
class DiffTab(_TabBase):
    """两轮对账页签：选两份 ``ScanResult`` JSON → ``scan.diff_scans`` → 对账集合。"""

    TITLE = "两轮对账"

    def __init__(self, data_dir=None):
        _TabBase.__init__(self, data_dir)
        qt = _qt()
        self.widget = qt["QWidget"]()
        root = qt["QVBoxLayout"](self.widget)

        prev_row = qt["QHBoxLayout"]()
        prev_row.addWidget(qt["QLabel"]("上轮结果 JSON（scan --json 产物）："))
        self.previous_edit = qt["QLineEdit"]()
        prev_row.addWidget(self.previous_edit, 1)
        self.previous_button = qt["QPushButton"]("选择…")
        self.previous_button.clicked.connect(
            lambda: self._browse(self.previous_edit, "选择上轮 ScanResult JSON"))
        prev_row.addWidget(self.previous_button)
        root.addLayout(prev_row)

        cur_row = qt["QHBoxLayout"]()
        cur_row.addWidget(qt["QLabel"]("本轮结果 JSON（scan --json 产物）："))
        self.current_edit = qt["QLineEdit"]()
        cur_row.addWidget(self.current_edit, 1)
        self.current_button = qt["QPushButton"]("选择…")
        self.current_button.clicked.connect(
            lambda: self._browse(self.current_edit, "选择本轮 ScanResult JSON"))
        cur_row.addWidget(self.current_button)
        root.addLayout(cur_row)

        action_row = qt["QHBoxLayout"]()
        self.diff_button = qt["QPushButton"]("开始对账")
        self.diff_button.clicked.connect(self._on_diff)
        action_row.addWidget(self.diff_button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        splitter = qt["QSplitter"]()
        self.summary_group, self.summary_table = self._kv_group("对账概要")
        splitter.addWidget(self.summary_group)
        detail_box = qt["QGroupBox"]("逐条对账（新增违规 / 已修复 / 持续违规 / 稳定 / 内容变动）")
        detail_layout = qt["QVBoxLayout"](detail_box)
        self.diff_table = self._make_table(fmt.DIFF_COLUMNS)
        detail_layout.addWidget(self.diff_table)
        splitter.addWidget(detail_box)
        root.addWidget(splitter, 1)

        self.text_view = qt["QPlainTextEdit"]()
        self.text_view.setReadOnly(True)
        self.text_view.setPlaceholderText("对账结论文本（可复制）")
        root.addWidget(self.text_view)

    def _browse(self, edit, title):
        qt = _qt()
        path, _filter = qt["QFileDialog"].getOpenFileName(
            self.widget, title, "", "JSON (*.json);;全部文件 (*)")
        if path:
            edit.setText(path)

    def _on_diff(self):
        previous = self.previous_edit.text().strip()
        current = self.current_edit.text().strip()
        if previous and current:
            self.diff(previous, current)

    def diff(self, previous_path, current_path):
        """对账两份结果并刷新界面；返回 :class:`~labelcheck.scan.diff.DiffResult`。"""
        try:
            result = services.diff_files(previous_path, current_path)
        except Exception as exc:  # noqa: BLE001
            qt = _qt()
            self.text_view.setPlainText("对账失败：{0}".format(exc))
            qt["QMessageBox"].warning(self.widget, "对账失败", str(exc))
            return None
        self._render(result)
        return result

    def _render(self, result):
        self._fill_table(self.summary_table, fmt.diff_summary(result))
        self._fill_table(self.diff_table, fmt.diff_rows(result))
        lines = ["两轮对账结果"]
        for label, value in fmt.diff_summary(result):
            lines.append("  {0}：{1}".format(label, value))
        for key, title in fmt.DIFF_SECTIONS:
            entries = getattr(result, key)
            if not entries:
                continue
            lines.append("{0}（{1}）：".format(title, len(entries)))
            for entry in entries:
                lines.append("  - {0}（{1}）".format(
                    entry.card_id or entry.identity, entry.path))
        self.text_view.setPlainText("\n".join(lines))


# ------------------------------------------------------------------ 基准指标
class BenchmarkTab(_TabBase):
    """基准指标页签：``benchmark.run_benchmark`` → 三类指标 + 达标线。"""

    TITLE = "基准指标"

    def __init__(self, data_dir=None):
        _TabBase.__init__(self, data_dir)
        qt = _qt()
        self.widget = qt["QWidget"]()
        root = qt["QVBoxLayout"](self.widget)

        row = qt["QHBoxLayout"]()
        row.addWidget(qt["QLabel"]("基准（可多选，缺省全跑）："))
        self.only_edit = qt["QLineEdit"](",".join(BENCH_NAMES))
        self.only_edit.setToolTip("三类基准名，逗号分隔：{0}".format(", ".join(BENCH_NAMES)))
        row.addWidget(self.only_edit, 1)
        self.run_button = qt["QPushButton"]("运行基准")
        self.run_button.clicked.connect(self._on_run)
        row.addWidget(self.run_button)
        self.verdict_label = qt["QLabel"]("（未运行）")
        row.addWidget(self.verdict_label)
        root.addLayout(row)

        for name in BENCH_NAMES:
            root.addWidget(qt["QLabel"]("· {0}：{1}".format(name, BENCH_TITLES[name])))

        self.metrics_table = self._make_table(fmt.BENCH_COLUMNS)
        root.addWidget(self.metrics_table, 1)

        self.text_view = qt["QPlainTextEdit"]()
        self.text_view.setReadOnly(True)
        self.text_view.setPlaceholderText("基准结果文本（含说明与失败明细）")
        root.addWidget(self.text_view)

    def _on_run(self):
        self.run(self._parse_only())

    def _parse_only(self):
        raw = self.only_edit.text().strip()
        if not raw:
            return None
        names = [item.strip() for item in raw.split(",") if item.strip()]
        return names or None

    def run(self, only=None):
        """跑基准并刷新界面；返回 :class:`~labelcheck.benchmark.metrics.BenchReport`。"""
        try:
            report = services.run_bench(self._require_data_dir(), only=only)
        except Exception as exc:  # noqa: BLE001
            qt = _qt()
            self.text_view.setPlainText("基准运行失败：{0}".format(exc))
            self._fill_table(self.metrics_table, [])
            self.verdict_label.setText("运行失败")
            qt["QMessageBox"].warning(self.widget, "基准运行失败", str(exc))
            return None
        self._render(report)
        return report

    def _render(self, report):
        self._fill_table(self.metrics_table, fmt.bench_rows(report))
        self.text_view.setPlainText(fmt.bench_text(report))
        self.verdict_label.setText("全部达标" if report.passed else "存在未达标")


# ------------------------------------------------------------------ 规则库与依据
class RulesTab(_TabBase):
    """规则库与依据页签：规则库坐标 + 依据清单 + 规则/映射条目。"""

    TITLE = "规则库与依据"

    def __init__(self, data_dir=None):
        _TabBase.__init__(self, data_dir)
        qt = _qt()
        self.widget = qt["QWidget"]()
        root = qt["QVBoxLayout"](self.widget)

        row = qt["QHBoxLayout"]()
        self.refresh_button = qt["QPushButton"]("刷新")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        self.coordinate_label = qt["QLabel"]("（未加载）")
        row.addWidget(self.coordinate_label, 1)
        root.addLayout(row)

        splitter = qt["QSplitter"]()
        docs_box = qt["QGroupBox"]("依据清单")
        docs_layout = qt["QVBoxLayout"](docs_box)
        self.docs_table = self._make_table(fmt.DOCUMENT_COLUMNS)
        docs_layout.addWidget(self.docs_table)
        splitter.addWidget(docs_box)
        mapping_box = qt["QGroupBox"]("字段映射（容器键 → 国标字段）")
        mapping_layout = qt["QVBoxLayout"](mapping_box)
        self.mapping_table = self._make_table(fmt.MAPPING_COLUMNS)
        mapping_layout.addWidget(self.mapping_table)
        splitter.addWidget(mapping_box)
        root.addWidget(splitter, 1)

        rules_box = qt["QGroupBox"]("规则条目（生效在前）")
        rules_layout = qt["QVBoxLayout"](rules_box)
        self.rules_table = self._make_table(fmt.RULE_COLUMNS)
        rules_layout.addWidget(self.rules_table)
        root.addWidget(rules_box, 2)

        self.text_view = qt["QPlainTextEdit"]()
        self.text_view.setReadOnly(True)
        root.addWidget(self.text_view)

    def refresh(self):
        """加载规则库并刷新界面；返回 :class:`~labelcheck.gui.services.RulesOverview`。"""
        try:
            overview = services.rules_overview(self._require_data_dir())
        except Exception as exc:  # noqa: BLE001
            qt = _qt()
            self.text_view.setPlainText("规则库加载失败：{0}".format(exc))
            self.coordinate_label.setText("加载失败")
            qt["QMessageBox"].warning(self.widget, "规则库加载失败", str(exc))
            return None
        self._render(overview)
        return overview

    def _render(self, overview):
        self.coordinate_label.setText(overview.ruleset.coordinate)
        self._fill_table(self.docs_table, fmt.document_rows(overview.ruleset))
        self._fill_table(self.mapping_table, fmt.mapping_rows(overview.mapping_table))
        self._fill_table(self.rules_table, fmt.rule_rows(overview.ruleset))
        self.text_view.setPlainText(fmt.rules_text(overview))


# ------------------------------------------------------------------ 关于
class AboutTab(_TabBase):
    """关于页签：定位、版本、免责声明（单一来源取自包 ``__init__``）。"""

    TITLE = "关于"

    def __init__(self, data_dir=None):
        _TabBase.__init__(self, data_dir)
        qt = _qt()
        self.widget = qt["QWidget"]()
        root = qt["QVBoxLayout"](self.widget)
        self.browser = qt["QTextBrowser"]()
        self.browser.setOpenExternalLinks(True)
        root.addWidget(self.browser)
        self.render()

    def render(self):
        lines = [
            "<h2>AI 生成合成内容标识合规核查器</h2>",
            "<p><b>版本</b>：{0}</p>".format(__version__),
            "<p><b>定位</b>：{0}</p>".format(POSITIONING),
            "<p><b>免责声明</b>：{0}</p>".format(DISCLAIMER),
            "<p>以《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号）与强制性"
            "国家标准 GB 45438-2025 为规则源；显式要素核验 + 隐式元数据字段核验 + "
            "完整性分级 + 批量扫描与两轮对账 + 合规证据链导出。</p>",
            "<p><b>全本地核查、零上传</b>：本工具不访问网络，不上传任何被核查内容；"
            "结论由确定性规则产生（零 LLM 依赖）。</p>",
            "<p><b>合规辅助</b>：本工具不提供任何去水印/标识规避功能。</p>",
        ]
        self.browser.setHtml("".join(lines))


#: 页签顺序（主窗口据此装配）
TAB_CLASSES = (SingleCheckTab, BatchScanTab, DiffTab, BenchmarkTab, RulesTab, AboutTab)

__all__ = [
    "NO_DATA_DIR_HINT",
    "SingleCheckTab", "BatchScanTab", "DiffTab", "BenchmarkTab", "RulesTab", "AboutTab",
    "TAB_CLASSES",
]
