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


# ------------------------------------------------------------------ M3 追加守门
def test_scan_and_report_modules_do_not_import_openpyxl_at_top_level():
    """``openpyxl`` 只能在函数体内**惰性导入**——否则无 report extra 的环境连 CLI 都跑不起来。

    ``scan/`` 与 ``report/`` 是 M3 新模块；``report`` 允许用第三方重件（在
    ``ALLOWED_THIRD_PARTY_MODULES`` 内），但**顶层**导入会让 ``import labelcheck.report``
    在没有 openpyxl 的机器上直接失败——与"缺失降级为 CSV，exit 0 不崩"（plan/04 §八.2）矛盾。
    """
    violations = []
    for sub in ("scan", "report"):
        for path in sorted((SRC / sub).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for module_name, lineno in _top_level_imports(tree):
                if module_name.split(".")[0] == "openpyxl":
                    violations.append("{0}:{1}".format(_rel(path), lineno))
    assert not violations, (
        "openpyxl 出现在模块顶层（须在函数体内惰性导入，缺失时降级 CSV）：\n"
        + "\n".join(violations))


def test_scan_module_has_no_third_party_top_level_imports():
    """``scan/`` 不在豁免名单内 → 必须零第三方（纯 stdlib）。"""
    violations = []
    for path in sorted((SRC / "scan").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module_name, lineno in _top_level_imports(tree):
            if _module_is_third_party(module_name):
                violations.append("{0}:{1} imports {2}".format(_rel(path), lineno, module_name))
    assert not violations, "scan 模块出现第三方顶层依赖：\n" + "\n".join(violations)


# ------------------------------------------------------------------ M4 追加守门
def test_benchmark_module_has_no_third_party_top_level_imports():
    """``benchmark/`` 不在豁免名单内 → 必须零第三方（纯规则通路，FR-11）。"""
    violations = []
    for path in sorted((SRC / "benchmark").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module_name, lineno in _top_level_imports(tree):
            if _module_is_third_party(module_name):
                violations.append("{0}:{1} imports {2}".format(_rel(path), lineno, module_name))
    assert not violations, "benchmark 模块出现第三方顶层依赖：\n" + "\n".join(violations)


def test_benchmark_module_uses_no_system_clock_or_random():
    """基准可复现前提：``benchmark/`` 不得调用系统时钟或 stdlib ``random``。

    （``test_no_stdlib_random_in_generators_or_core`` 已覆盖 ``random`` 的 import；
    此处补 ``datetime.now``/``time.time`` 这类**调用**，与引擎同一条确定性纪律。）
    """
    forbidden = ("datetime.now(", "datetime.today()", "time.time()", "utcnow(")
    violations = []
    for path in sorted((SRC / "benchmark").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                violations.append("{0} 含 {1}".format(_rel(path), token))
    assert not violations, "基准源码使用系统时钟（产物将不可复现）：\n" + "\n".join(violations)


# ------------------------------------------------------------------ M5 追加守门
def test_packaging_module_has_no_pyinstaller_top_level_import():
    """``packaging/`` 顶层不得 import PyInstaller——否则无 pkg extra 的环境连
    ``import labelcheck.packaging``（及其测试）都跑不起来。

    PyInstaller 只出现在 ``tools/*.spec`` 与 ``tools/build_exe.py`` 里。
    """
    violations = []
    for path in sorted((SRC / "packaging").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module_name, lineno in _top_level_imports(tree):
            if module_name.split(".")[0] == "PyInstaller":
                violations.append("{0}:{1}".format(_rel(path), lineno))
    assert not violations, "packaging 顶层 import 了 PyInstaller：\n" + "\n".join(violations)


def test_packaging_module_has_no_third_party_top_level_imports():
    """``packaging/`` 不在第三方豁免名单内 → 必须零第三方顶层依赖。"""
    violations = []
    for path in sorted((SRC / "packaging").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module_name, lineno in _top_level_imports(tree):
            if _module_is_third_party(module_name):
                violations.append("{0}:{1} imports {2}".format(_rel(path), lineno, module_name))
    assert not violations, "packaging 模块出现第三方顶层依赖：\n" + "\n".join(violations)


def test_gui_service_layer_has_no_third_party_top_level_imports():
    """``gui/services.py`` 与 ``gui/format.py`` 顶层零第三方（无 PySide6 也能导入）。"""
    violations = []
    for name in ("services.py", "format.py"):
        path = SRC / "gui" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module_name, lineno in _top_level_imports(tree):
            if _module_is_third_party(module_name):
                violations.append("{0}:{1} imports {2}".format(_rel(path), lineno, module_name))
    assert not violations, "GUI 服务层出现第三方顶层依赖：\n" + "\n".join(violations)
