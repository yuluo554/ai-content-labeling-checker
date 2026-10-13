# -*- coding: utf-8 -*-
"""桌面界面（PySide6，可选依赖 extra ``gui``）：**只渲染引擎结果，零判定逻辑**。

分层与纪律见 plan/03 §一 / plan/04 §十二：

- :mod:`.services` —— **零 Qt** 的服务层：唯一引擎调用点（``engine.check_file`` /
  ``scan.scan_target`` / ``scan.diff_scans`` / ``benchmark.run_benchmark``）；
  无 PySide6 的机器也能导入（故服务层可被普通 pytest 全覆盖）；
- :mod:`.format` —— 文本/表格渲染：引擎字段 → 展示行（零判定）；
- :mod:`.tabs` —— 六个页签控件（单件核验 / 批量扫描 / 两轮对账 / 基准指标 / 规则库与依据 / 关于）；
- :mod:`.main_window` —— 主窗口与入口（**本模块顶层 import PySide6**）。

**惰性导入纪律**：``cli/`` 顶层不得 import 本包（AST 守门测试断言），故 ``labelcheck gui``
子命令在函数体内导入 :func:`labelcheck.gui.main_window.main`。无 GUI 依赖的环境
（CI 的 ``.[dev]`` 通路）因此仍可跑 CLI 与全量测试。

本模块**不**在顶层导入子模块（避免 ``import labelcheck.gui`` 就把 PySide6 拖进来）；
需要时显式 ``from labelcheck.gui import services``。
"""

__all__ = []
