# -*- coding: utf-8 -*-
"""GUI 主窗口与入口（PySide6）。

**本模块顶层 import PySide6**——这正是架构守门测试允许的（``gui/`` 在豁免名单内），
但 ``cli/`` 顶层**禁止** import 它（CLI 必须能在无 GUI 依赖的环境跑）。故
``labelcheck gui`` 子命令在函数体内惰性导入本模块（见 ``cli/main.py``）。

主窗口只做两件事：**装配页签** + **统一下发数据目录**。所有"干活"都在页签里，
而页签只调 :mod:`labelcheck.gui.services`（后者只调引擎）——判定逻辑不在这条链上。
"""

import sys

from .. import POSITIONING, __version__
from ..errors import LabelCheckError
from ..paths import ENV_VAR, find_data_dir
from . import services
from .tabs import TAB_CLASSES


def _resolve_initial_data_dir(explicit=None):
    """定位初始数据目录（失败返回 ``None``——界面允许用户稍后再选）。"""
    try:
        return find_data_dir(explicit, require=False)
    except LabelCheckError:
        return None


class MainWindow(object):
    """主窗口：六页签 + 顶部数据目录选择条。

    刻意**不做** QMainWindow 子类（组合优于继承）：主窗口的行为面很小，装配即可，
    便于 offscreen 测试直接调用 ``build()`` 拿到控件再逐页签驱动。
    """

    TITLE = "AI 生成内容标识合规核查器 {0} — {1}".format(__version__, POSITIONING)

    def __init__(self, data_dir=None):
        qt = _qt()
        self.window = qt["QMainWindow"]()
        self.window.setWindowTitle(self.TITLE)
        self.window.resize(1180, 820)

        central = qt["QWidget"]()
        layout = qt["QVBoxLayout"](central)

        bar = qt["QHBoxLayout"]()
        bar.addWidget(qt["QLabel"]("数据目录："))
        self.data_dir_edit = qt["QLineEdit"]()
        bar.addWidget(self.data_dir_edit, 1)
        self.browse_button = qt["QPushButton"]("选择…")
        self.browse_button.clicked.connect(self._on_browse_data_dir)
        bar.addWidget(self.browse_button)
        self.reload_button = qt["QPushButton"]("重新加载")
        self.reload_button.clicked.connect(self._on_reload)
        bar.addWidget(self.reload_button)
        layout.addLayout(bar)

        self.status_label = qt["QLabel"]("")
        layout.addWidget(self.status_label)

        self.tabs = qt["QTabWidget"]()
        self.tab_objects = []
        for tab_cls in TAB_CLASSES:
            tab = tab_cls(data_dir)
            self.tab_objects.append(tab)
            self.tabs.addTab(tab.widget, tab.TITLE)
        layout.addWidget(self.tabs, 1)

        self.window.setCentralWidget(central)

        self.data_dir = None
        self.set_data_dir(data_dir)

    # ------------------------------------------------------------------ 数据目录
    def set_data_dir(self, data_dir):
        """设置数据目录并下发到全部页签（``None`` = 未定位，页签给提示）。"""
        self.data_dir = data_dir
        text = str(data_dir) if data_dir else ""
        self.data_dir_edit.setText(text)
        for tab in self.tab_objects:
            tab.set_data_dir(data_dir)
        if data_dir:
            self.status_label.setText("数据目录：{0}".format(text))
        else:
            self.status_label.setText(
                "未定位数据目录——请点『选择…』指定仓库 data/ 目录（或设置环境变量 {0}）。".format(
                    ENV_VAR))

    def _on_browse_data_dir(self):
        qt = _qt()
        path = qt["QFileDialog"].getExistingDirectory(self.window, "选择数据目录（含 rules/registry.json）")
        if path:
            self.set_data_dir(path)

    def _on_reload(self):
        self.set_data_dir(self.data_dir)
        self._refresh_rules_tab()

    def _refresh_rules_tab(self):
        """数据目录就绪时自动刷新"规则库与依据"页签（未就绪则跳过，不弹错）。"""
        if not self.data_dir:
            return
        for tab in self.tab_objects:
            if getattr(tab, "TITLE", "") == "规则库与依据":
                tab.refresh()

    def show(self):
        self.window.show()


def _qt():
    """惰性取 Qt 符号（本模块整体在 ``gui`` 惰性导入链上，顶层导入亦可）。"""
    from PySide6.QtWidgets import (
        QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
        QTabWidget, QVBoxLayout, QWidget,
    )
    return locals()


def build_app(argv=None, data_dir=None):
    """构造 ``(QApplication, MainWindow)``（供入口与 offscreen 测试共用）。"""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(list(argv or []))
    window = MainWindow(data_dir=data_dir)
    return app, window


def main(argv=None, data_dir=None):
    """GUI 入口：返回进程退出码（0 = 正常关闭）。"""
    argv = list(sys.argv if argv is None else argv)
    initial = _resolve_initial_data_dir(data_dir)
    app, window = build_app(argv=argv[:1], data_dir=initial)
    window.show()
    return app.exec()


__all__ = ["MainWindow", "build_app", "main"]
