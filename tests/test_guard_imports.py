"""守门测试（架构纪律的机器化，不是口号）：AST import 门 + 核心层零第三方。

**为什么用 AST 静态断言而不是运行期 sys.modules**：pytest 收集期会导入测试模块，
模块级 ``sys.modules`` 断言会产生假失败（系列踩坑）。AST 只读源码，可靠。
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "labelcheck"

#: 允许 import 第三方重件的模块（其余核心模块必须零第三方）
ALLOWED_THIRD_PARTY_MODULES = ("gui", "packaging", "report")

#: 第三方包名 → 允许出现的模块前缀
THIRD_PARTY_PACKAGES = ("PySide6", "openpyxl", "PyInstaller", "pytest", "yaml")

STDLIB_OR_LOCAL = set()


def _iter_py_files():
    for path in sorted(SRC.rglob("*.py")):
        yield path


def _module_is_third_party(module_name):
    if not module_name:
        return False
    root = module_name.split(".")[0]
    return root in THIRD_PARTY_PACKAGES


def _rel(path):
    return path.relative_to(SRC.parent.parent).as_posix()


def _top_level_imports(tree):
    """收集模块**顶层**（非函数体内）的 import 模块名。"""
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # 相对导入（level>0）不是第三方
            if node.level > 0:
                continue
            if node.module:
                names.append((node.module, node.lineno))
    return names


def _is_allowed_module(path):
    rel_parts = path.relative_to(SRC).parts
    return bool(rel_parts) and rel_parts[0] in ALLOWED_THIRD_PARTY_MODULES


def test_core_modules_have_no_third_party_top_level_imports():
    """核心层（除 gui/packaging/report）不得在模块顶层 import 第三方包。"""
    violations = []
    for path in _iter_py_files():
        if _is_allowed_module(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module_name, lineno in _top_level_imports(tree):
            if _module_is_third_party(module_name):
                violations.append("{0}:{1} imports {2}".format(_rel(path), lineno, module_name))
    assert not violations, "核心层出现第三方依赖（架构违规）：\n" + "\n".join(violations)


def test_cli_modules_never_import_gui_at_top_level():
    """CLI 顶层不得 import GUI/PySide6——保证无 GUI 依赖环境也能跑 CLI 与全量测试。

    ``gui`` 子命令（M5）必须惰性导入（函数体内）。
    """
    violations = []
    for path in sorted((SRC / "cli").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module_name, lineno in _top_level_imports(tree):
            root = module_name.split(".")[0]
            if root in ("gui", "PySide6"):
                violations.append("{0}:{1} imports {2}".format(_rel(path), lineno, module_name))
    assert not violations, "CLI 顶层 import 了 GUI（须改为函数体内惰性导入）：\n" + "\n".join(violations)


def test_cli_never_imports_pyside_anywhere_in_ast():
    """CLI 在 M0 不得 import PySide6（含函数体内）——GUI 属 M5。

    用 AST 而非子串扫描：docstring/注释里提到 PySide6 是**说明**，不是依赖；
    子串扫描会把文档一并判违规（"扫描器扫描自己"的假阳性）。
    """
    violations = []
    for path in sorted((SRC / "cli").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] == "PySide6":
                    violations.append("{0}:{1} imports {2}".format(_rel(path), node.lineno, name))
    assert not violations, "CLI import 了 PySide6（M5 才引入）：\n" + "\n".join(violations)


def test_gui_command_is_lazily_imported_when_added():
    """``gui`` 子命令（M5）必须以函数体内惰性导入出现，绝不在模块顶层。

    当前 M0 尚无 gui 子命令，此处仅断言"顶层不得出现 gui 导入"这一不变式；
    M5 引入后本测试继续生效（惰性导入不会被顶层扫描命中）。
    """
    violations = []
    for path in sorted((SRC / "cli").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module_name, lineno in _top_level_imports(tree):
            if module_name.split(".")[0] in ("gui", "PySide6"):
                violations.append("{0}:{1} imports {2}".format(_rel(path), lineno, module_name))
    assert not violations, "GUI 依赖出现在 CLI 模块顶层（须惰性导入）：\n" + "\n".join(violations)


def test_no_network_imports_in_core():
    """NFR-1 全本地零上传：核心层不得 import 网络栈。"""
    network_roots = ("socket", "http", "urllib", "requests", "ftplib", "smtplib", "telnetlib")
    violations = []
    for path in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in network_roots:
                    violations.append("{0}: imports {1}".format(_rel(path), name))
    assert not violations, "核心层出现网络依赖（违反全本地零上传）：\n" + "\n".join(violations)


def test_no_stdlib_random_in_generators_or_core():
    """确定性纪律：核心层禁用 stdlib ``random``（须用 labelcheck.rng.splitmix64）。"""
    violations = []
    for path in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "random":
                        violations.append("{0}:{1}".format(_rel(path), node.lineno))
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "random":
                violations.append("{0}:{1}".format(_rel(path), node.lineno))
    assert not violations, "核心层 import 了 stdlib random（须用 splitmix64）：\n" + "\n".join(violations)


def test_declared_dependencies_is_empty():
    """pyproject 核心 ``dependencies`` 必须为空（重件走 extras）。"""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    # 用 toml 解析（3.8 无 tomllib；此处做轻量文本断言，避免引入第三方）
    assert "dependencies = []" in text, "核心 dependencies 必须为空数组"

    # 同时防"改名绕开"：脚本入口必须指向 labelcheck.cli.main:main
    assert 'labelcheck = "labelcheck.cli.main:main"' in text


def test_all_declared_python_files_are_parseable():
    """全部源码必须能被 AST 解析（语法/编码问题的早期拦截）。"""
    for path in _iter_py_files():
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
