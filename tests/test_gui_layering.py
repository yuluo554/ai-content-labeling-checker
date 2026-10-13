"""GUI 分层守门（AST 静态断言）+ 服务层零 Qt 纪律。

**为什么用 AST 而不是运行期 ``sys.modules``**：pytest 收集期会导入测试模块，
模块级断言会产生假失败（系列踩坑）。AST 只读源码，可靠（同 ``test_guard_imports``）。

本文件锁死三条**架构不变式**（plan/03 §一 分层图 / plan/04 §十二）：

1. **服务层零 Qt**：``gui/services.py`` 与 ``gui/format.py`` 不得 import PySide6
   （含函数体内）——否则"无 GUI 依赖也能跑服务层测试"这条退路就断了；
2. **服务层零判定逻辑**：``gui/services.py`` 只许调引擎入口，不得 import
   ``rules.rule.evaluate`` / ``engine.explicit`` / ``engine.implicit`` 这类**判定器**
   （调 ``engine.check_file`` 编排入口是允许且必需的）；
3. **CLI 顶层不得 import GUI**（M0 已有断言，此处补"gui 子命令惰性导入"的正面断言）。
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "labelcheck"
GUI = SRC / "gui"


def _rel(path):
    return path.relative_to(ROOT).as_posix()


def _imports(path):
    """收集文件内**全部**（含函数体内）import 的模块名。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def _top_level_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def test_gui_package_exists_with_expected_modules():
    for name in ("__init__.py", "services.py", "format.py", "tabs.py", "main_window.py"):
        assert (GUI / name).is_file(), "gui 缺模块：{0}".format(name)


def test_services_and_format_never_import_pyside():
    """服务层与渲染层必须零 Qt——这是"无 GUI 环境也能测服务层"的地基。"""
    violations = []
    for name in ("services.py", "format.py", "__init__.py"):
        path = GUI / name
        for module in _imports(path):
            if module.split(".")[0] == "PySide6":
                violations.append("{0}: imports {1}".format(_rel(path), module))
    assert not violations, (
        "GUI 服务层/渲染层出现 PySide6（应只存在于 tabs.py/main_window.py）：\n"
        + "\n".join(violations))


def test_gui_package_init_does_not_import_pyside():
    """``import labelcheck.gui`` 本身不得拖入 PySide6（否则 CLI 惰性导入形同虚设）。"""
    for module in _top_level_imports(GUI / "__init__.py"):
        assert module.split(".")[0] != "PySide6", "__init__ 顶层 import 了 PySide6"


def test_services_only_calls_engine_entry_points():
    """服务层不得 import 判定器（evaluate / explicit / implicit / integrity）。

    ``engine.check_file`` 是**编排入口**（允许且必需）；把判定器搬进 GUI 会让界面
    重写一遍口径，与 CLI 分叉——这正是守门要拦的。
    """
    forbidden = {
        "labelcheck.rules.rule",
        "labelcheck.engine.explicit",
        "labelcheck.engine.implicit",
        "labelcheck.engine.integrity",
    }
    violations = []
    for module in _imports(GUI / "services.py"):
        if module in forbidden:
            violations.append(module)
    assert not violations, (
        "GUI 服务层 import 了判定器（判定逻辑只许存在于引擎）：\n" + "\n".join(violations))


def test_services_imports_the_four_engine_entry_points():
    """反向断言：服务层必须确实调那四个入口（防"占位却从不调用"的空壳）。"""
    text = (GUI / "services.py").read_text(encoding="utf-8")
    for token in ("check_file", "scan_target", "diff_scans", "run_benchmark"):
        assert token in text, "服务层未引用引擎入口：{0}".format(token)


def test_tabs_module_does_not_import_pyside_at_top_level():
    """``tabs.py`` 顶层不得 import PySide6——它用函数体内 ``_qt()`` 惰性取符号。

    这样 ``import labelcheck.gui.tabs``（无显示环境）也能成功，只有**构造控件**时才需要 Qt。
    """
    violations = [
        module for module in _top_level_imports(GUI / "tabs.py")
        if module.split(".")[0] == "PySide6"
    ]
    assert not violations, "tabs.py 顶层 import 了 PySide6：{0}".format(violations)


def test_cli_gui_subcommand_imports_gui_lazily():
    """``gui`` 子命令必须在**函数体内**导入 GUI（顶层 import 会打挂无 GUI 环境的 CLI）。"""
    cli = SRC / "cli" / "main.py"
    top = _top_level_imports(cli)
    assert not any(m.split(".")[0] in ("gui", "PySide6") for m in top), \
        "CLI 顶层 import 了 GUI"

    tree = ast.parse(cli.read_text(encoding="utf-8"), filename=str(cli))
    in_func = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if not isinstance(sub, ast.ImportFrom):
                    continue
                # 匹配 `from ..gui import main_window`（相对导入 level=2, module="gui"）
                module = (sub.module or "").split(".")[-1]
                names = [alias.name for alias in sub.names]
                if module == "gui" or "main_window" in names:
                    in_func.add(node.name)
    assert "cmd_gui" in in_func, "cmd_gui 未在函数体内惰性导入 gui.main_window"
