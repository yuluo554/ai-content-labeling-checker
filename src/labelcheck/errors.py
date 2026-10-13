"""异常类型与 CLI 退出码（**单一定义源**）。

退出码语义见 plan/04-模块详设.md §二.2，测试逐码锁死：

===== ==============================================================
 码     含义
===== ==============================================================
 0      完成且未发现 fail（允许存在 unknown/skipped）
 1      完成但发现 fail（核查出不合规）
 2      用法/输入错误（参数错、文件不存在、JSON 坏、card 校验失败）
 3      环境/依赖错误（规则库缺失、数据目录定位失败、可选依赖缺失需降级）
===== ==============================================================

注意：``check`` 的退出码 1 表示"检出不合规"，不是"程序出错"——这是脚本化
使用的关键分流点，不是错误。
"""


# --- 退出码常量（唯一来源，任何模块不得硬编码数字） ---
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_ENV = 3


class LabelCheckError(Exception):
    """本工具所有自定义异常的基类。"""

    exit_code = EXIT_ENV


class UsageError(LabelCheckError):
    """用法或输入错误（坏 JSON、缺文件、card 校验失败等）→ exit 2。"""

    exit_code = EXIT_USAGE


class InputError(UsageError):
    """输入内容本身不合法（card 结构/取值问题）→ exit 2。"""

    exit_code = EXIT_USAGE


class EnvironmentError_(LabelCheckError):
    """环境/依赖问题（数据目录定位失败、规则库缺失/损坏）→ exit 3。

    末尾下划线避免与内置 ``EnvironmentError``（= OSError 别名）混淆。
    """

    exit_code = EXIT_ENV


class RulesetError(EnvironmentError_):
    """规则库加载或结构校验失败 → exit 3。"""

    exit_code = EXIT_ENV


__all__ = [
    "EXIT_OK",
    "EXIT_FINDINGS",
    "EXIT_USAGE",
    "EXIT_ENV",
    "LabelCheckError",
    "UsageError",
    "InputError",
    "EnvironmentError_",
    "RulesetError",
]
