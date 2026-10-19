"""CI workflow 守门测试。

**为什么值得单测**（系列实录取证）：step 名含「冒号+空格」的非法 YAML 会让整份
workflow 非法 → GitHub **不建任何 job**（run 0 秒失败、`jobs=0`），而 GitHub 端
该 workflow 的 `state` 仍显示 `active`、文件字节也洁净——**看状态、看字节都查不出，
只有真解析或真跑才暴露**。故这里用 pyyaml（dev extra）真解析。

另外锁死两件事：
1. 每个 job 必须有 ``runs-on`` 与 ``steps``（缺了就是"不跑的 job"）；
2. 每个 ``actions/checkout`` step 必须 ``fetch-depth: 0``——否则历史类守门测试在
   CI 里只看到 1 个提交，**静默削弱成空验**。
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="需要 pyyaml（dev extra）解析 workflow")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT / ".github" / "workflows"


def _workflow_files():
    files = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
    assert files, "未找到任何 workflow 文件"
    return files


def test_workflow_yaml_guard_catches_colon_space_in_step_name():
    """**阳性对照**：确认 YAML 守门能抓住真实故障形态。

    实测故障（系列取证）：step 名是不带引号的纯量且含「冒号+空格」→ 整份 workflow
    非法 → GitHub **不建任何 job**（run 0 秒失败、jobs=0），而平台端 state 仍显示
    active、文件字节也洁净 —— 看状态、看字节都查不出。故这里必须真解析。
    """
    broken = (
        "name: Bad\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: Run tests (GUI offscreen: QT_QPA_PLATFORM=offscreen)\n"
        "        run: echo hi\n"
    )
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(broken)

    # 同样语义、换成方括号即合法 → 证明拒绝的是写法而非"什么都拒绝"
    fixed = broken.replace("(GUI offscreen: QT_QPA_PLATFORM=offscreen)",
                           "[GUI offscreen - QT_QPA_PLATFORM offscreen]")
    assert isinstance(yaml.safe_load(fixed), dict)


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_workflow_is_parseable_yaml(path):
    """非法 YAML → GitHub 不建任何 job（最隐蔽的"从未验证过"故障）。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        pytest.fail("{0} 不是合法 YAML：{1}".format(path.name, exc))
    assert isinstance(data, dict), "workflow 顶层必须是映射"


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_every_job_has_runs_on_and_steps(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = data.get("jobs")
    assert isinstance(jobs, dict) and jobs, "{0} 没有定义 jobs".format(path.name)

    for job_id, job in jobs.items():
        assert isinstance(job, dict), "{0}: job {1} 结构异常".format(path.name, job_id)
        assert "runs-on" in job or "uses" in job, (
            "{0}: job {1} 缺 runs-on".format(path.name, job_id)
        )
        assert "steps" in job, "{0}: job {1} 缺 steps".format(path.name, job_id)
        assert isinstance(job["steps"], list) and job["steps"], (
            "{0}: job {1} 的 steps 为空".format(path.name, job_id)
        )


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_checkout_steps_use_full_history(path):
    """历史扫描类守门测试的环境前提：checkout 必须 fetch-depth: 0。"""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    offenders = []
    for job_id, job in data.get("jobs", {}).items():
        for index, step in enumerate(job.get("steps", [])):
            uses = str(step.get("uses", ""))
            if uses.startswith("actions/checkout"):
                depth = (step.get("with") or {}).get("fetch-depth")
                if depth != 0:
                    offenders.append("{0}: job {1} step[{2}] fetch-depth={3!r}".format(
                        path.name, job_id, index, depth))
    assert not offenders, (
        "checkout 未取全量历史（历史类守门会静默空验）：\n" + "\n".join(offenders)
    )


def test_ci_covers_supported_python_on_both_oses():
    """矩阵须覆盖 windows×3.12 + ubuntu×3.12（**规格变更 2026-10-19**）。

    原断言要求 ``windows/py3.8``——Python 3.8 已于 2024-10-07 EOL，
    2026-10-19 决策 D-1 把 ``requires-python`` 抬到 ``>=3.12`` 并删掉 3.8 作业。
    本测试随之改为"两 OS 都须有 3.12，且不得再有已 EOL 的 3.8 作业"。
    """
    data = yaml.safe_load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"))
    windows_versions = set()
    ubuntu_versions = set()
    for job in data.get("jobs", {}).values():
        strategy = job.get("strategy") or {}
        for entry in (strategy.get("matrix") or {}).get("include", []) or []:
            os_name = str(entry.get("os", ""))
            version = str(entry.get("python-version"))
            if os_name.startswith("windows"):
                windows_versions.add(version)
            elif os_name.startswith("ubuntu"):
                ubuntu_versions.add(version)
    assert "3.12" in windows_versions, "矩阵须含 windows/py3.12"
    assert "3.12" in ubuntu_versions, "矩阵须含 ubuntu/py3.12"
    assert "3.8" not in (windows_versions | ubuntu_versions), (
        "Python 3.8 已 EOL（2024-10-07），CI 不得再有 3.8 作业")


def test_ci_installs_dev_extras_so_guard_tests_can_run():
    """CI 必须装 dev extras——否则 pyyaml 缺席会让本文件的守门整体 skip（静默少跑）。"""
    text = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
    assert "[dev]" in text, "CI 必须安装 .[dev]（含 pyyaml，供 workflow 守门测试）"


def test_ci_installs_report_extra_so_xlsx_tests_run():
    """CI 必须装 ``report`` extra——否则 XLSX 确定性测试**每次 skip**（D46）。

    修前实测：``tests/test_report.py::test_xlsx_is_deterministic_even_without_timestamp``
    用 ``pytest.importorskip("openpyxl")``，而 CI 从不安装 openpyxl → 该用例在 CI 里
    永远 skip，"有测试"变成"从未验证过"。正确修法是让 CI 装 openpyxl（**不是**删
    ``importorskip``——那会把"可选依赖缺失"从降级变成硬失败）。

    本断言同时要求：装了 extra，且仍有 job 跑 XLSX 用例（防"装了但没跑"）。
    """
    data = yaml.safe_load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"))
    installs = []
    for job_id, job in data.get("jobs", {}).items():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if "pip install" in run and "report" in run:
                installs.append(job_id)
    assert installs, "CI 必须至少有一个 job 安装 report extra（openpyxl）"

    text = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
    assert "[dev,report]" in text or "[dev,gui,report]" in text or "[dev,gui,report,pkg]" in text, (
        "CI 必须显式安装 dev+report 组合（否则 XLSX 确定性测试仍被 skip）")


def test_ci_has_package_job_building_and_verifying_exe():
    """CI 必须有 ``package`` job 真构建 + 真验收 exe（D46）。

    修前：``packaging-guard`` 只跑 ``tests/test_packaging.py`` 的纯逻辑，exe 从不在
    CI 里构建——"发布物可复现"只存在于本机。本断言锁死三件事同时成立：

    1. 存在名为 ``package`` 的 job；
    2. 它跑 ``tools.build_exe``（真 PyInstaller 构建）；
    3. 它跑 ``tools.verify_package.py``（中立环境验收，断言数据目录落在 dist 内）。
    """
    data = yaml.safe_load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"))
    jobs = data.get("jobs") or {}
    assert "package" in jobs, "CI 缺少 package job（发布物无 CI 门禁）"
    job = jobs["package"]
    runs = "\n".join((step.get("run") or "") for step in job.get("steps", []))
    assert "tools.build_exe" in runs, "package job 必须真跑 tools.build_exe"
    assert "tools/verify_package.py" in runs, "package job 必须跑 tools/verify_package.py"
    # 真构建需要 PyInstaller 与 GUI 依赖
    assert "pkg" in runs, "package job 必须安装 pkg extra（PyInstaller）"
    assert "gui" in runs, "package job 必须安装 gui extra（GUI exe 需要 PySide6）"


def test_every_pytest_job_declares_a_collection_count_gate():
    """每个跑 pytest 的 job 都必须有**收集数对账**（D46）。

    为什么值得单测：收集数写死能拦住两类沉默失效——① ``collection error`` 让收集数
    变小，pytest 仍可能以 0 退出（取决于参数）；② 有人把"必须收集到全部用例"的
    断言悄悄放宽成"够用就行"。故这里要求：凡是 ``pytest tests`` 的 job，必须同时
    出现 ``--collect-only`` 与一个明确的期望数字。
    """
    data = yaml.safe_load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"))
    offenders = []
    for job_id, job in data.get("jobs", {}).items():
        steps = job.get("steps", [])
        runs = "\n".join((step.get("run") or "") for step in steps)
        if "pytest tests" not in runs:
            continue
        if "--collect-only" not in runs:
            offenders.append("{0}: 缺收集数对账步骤".format(job_id))
            continue
        if not any(token in runs for token in ('"447 tests collected"', '"463 tests collected"',
                                               '"18 tests collected"')):
            offenders.append("{0}: 收集数对账没有写死期望值".format(job_id))
    assert not offenders, (
        "以下 job 的收集数门禁不完整（防'少收集也绿'）：\n" + "\n".join(offenders))


def test_ci_actions_use_current_major_versions():
    """actions 必须用当前主版本（v7）——v4/v5 已收 Node.js 20 弃用警告（D46）。"""
    text = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
    assert "actions/checkout@v7" in text, "checkout 应升到 v7"
    assert "actions/setup-python@v7" in text, "setup-python 应升到 v7"
    for stale in ("actions/checkout@v4", "actions/setup-python@v5"):
        assert stale not in text, "仍在使用过旧 action：{0}".format(stale)
