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


def test_ci_covers_old_and_new_python_on_windows():
    """矩阵须覆盖 windows×{3.8, 3.12}（旧解释器只在 windows 守，见 plan/06 D16）。"""
    data = yaml.safe_load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"))
    versions = set()
    for job in data.get("jobs", {}).values():
        strategy = job.get("strategy") or {}
        for entry in (strategy.get("matrix") or {}).get("include", []) or []:
            if entry.get("os", "").startswith("windows"):
                versions.add(str(entry.get("python-version")))
    assert "3.8" in versions, "矩阵须含 windows/py3.8"
    assert "3.12" in versions, "矩阵须含 windows/py3.12"


def test_ci_installs_dev_extras_so_guard_tests_can_run():
    """CI 必须装 dev extras——否则 pyyaml 缺席会让本文件的守门整体 skip（静默少跑）。"""
    text = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
    assert "[dev]" in text, "CI 必须安装 .[dev]（含 pyyaml，供 workflow 守门测试）"
