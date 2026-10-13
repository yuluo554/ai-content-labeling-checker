"""打包支持测试（**零 PyInstaller 依赖**）：数据白名单 + 冻结态校验的验伪逻辑。

``labelcheck.packaging`` 顶层不 import PyInstaller（只在 spec/构建脚本里用），
故本文件在无 ``pkg`` extra 的环境也能跑。

覆盖：白名单只含运行必需子目录、缺件显式报错、``verify_dist`` 的**验伪分支**
（内嵌数据不在 dist 之内 / 未报告冻结态 / 规则数为 0 都必须判未通过——否则校验
就成了"验了个寂寞"的空验）。
"""

import json
from pathlib import Path

import pytest

from labelcheck.errors import EnvironmentError_
from labelcheck.packaging import (
    CLI_EXE_NAME, DATA_SUBDIRS, DIST_DATA_DIRNAME, GUI_EXE_NAME,
    assert_ready, build_datas, datas_manifest, default_dist_dir, missing_data_subdirs,
    neutral_env, verify_dist,
)
from labelcheck.packaging import repo_root as packaging_repo_root

from labelcheck.paths import ENV_VAR


# ------------------------------------------------------------------ 白名单
def test_data_subdirs_are_the_runtime_assets():
    assert set(DATA_SUBDIRS) == {"rules", "mapping", "truth", "parse", "samples", "knowledge"}
    assert "_private" not in DATA_SUBDIRS, "本地私有件不得进发行包"


def test_build_datas_maps_every_present_subdir(repo_root):
    datas = build_datas(repo_root / "data", root=repo_root)
    manifest = datas_manifest(datas)
    assert set(manifest) == set(DATA_SUBDIRS)
    for name, source in manifest.items():
        assert Path(source).is_dir(), "白名单源目录不存在：{0}".format(source)
    # 目标是 dist 内 data/<name>
    targets = [target for _source, target in datas]
    assert all(t.startswith(DIST_DATA_DIRNAME + "/") for t in targets)


def test_build_datas_skips_missing_subdirs(tmp_path):
    data = tmp_path / "data"
    (data / "rules").mkdir(parents=True)
    (data / "rules" / "registry.json").write_text("{}", encoding="utf-8")
    (data / "mapping").mkdir()
    datas = build_datas(data, root=tmp_path)
    assert set(datas_manifest(datas)) == {"rules", "mapping"}


def test_missing_data_subdirs_reports_gaps(tmp_path):
    data = tmp_path / "data"
    (data / "rules").mkdir(parents=True)
    missing = missing_data_subdirs(data, root=tmp_path)
    assert "mapping" in missing and "rules" not in missing


def test_assert_ready_raises_on_missing_subdir(tmp_path):
    data = tmp_path / "data"
    (data / "rules").mkdir(parents=True)
    with pytest.raises(EnvironmentError_):
        assert_ready(data, root=tmp_path)


def test_assert_ready_raises_without_sentinel(tmp_path):
    data = tmp_path / "data"
    for name in DATA_SUBDIRS:
        (data / name).mkdir(parents=True)
    with pytest.raises(EnvironmentError_):
        assert_ready(data, root=tmp_path)


def test_assert_ready_passes_on_repo_data(repo_root):
    assert assert_ready(repo_root / "data", root=repo_root) == repo_root / "data"


def test_default_dist_dir_and_repo_root(repo_root):
    assert packaging_repo_root() == repo_root
    assert default_dist_dir(repo_root) == repo_root / "dist"


# ------------------------------------------------------------------ verify_dist 验伪分支
def _fake_dist(tmp_path, embedded=True, sentinel=True, exe=True):
    """造一个假的 dist 目录（不依赖真 PyInstaller 产物）。"""
    dist = tmp_path / "dist"
    dist.mkdir()
    if embedded:
        data = dist / DIST_DATA_DIRNAME
        (data / "rules").mkdir(parents=True)
        if sentinel:
            (data / "rules" / "registry.json").write_text("{}", encoding="utf-8")
    if exe:
        (dist / "{0}.exe".format(CLI_EXE_NAME)).write_bytes(b"MZ fake")
    return dist


def test_verify_dist_fails_when_data_not_embedded(tmp_path):
    dist = _fake_dist(tmp_path, embedded=False)
    result = verify_dist(dist, run=False)
    assert result["ok"] is False
    assert any("未找到内嵌数据" in p for p in result["problems"])


def test_verify_dist_static_pass_when_embedded(tmp_path):
    dist = _fake_dist(tmp_path)
    result = verify_dist(dist, run=False)
    assert result["ok"] is True
    assert result["inside_dist"] is True
    assert result["data_dir"].endswith(DIST_DATA_DIRNAME)


def test_verify_dist_accepts_pyinstaller6_internal_layout(tmp_path):
    """PyInstaller 6 onedir 把数据放在 ``_internal/data``（也须识别）。"""
    dist = tmp_path / "dist"
    data = dist / "_internal" / DIST_DATA_DIRNAME
    (data / "rules").mkdir(parents=True)
    (data / "rules" / "registry.json").write_text("{}", encoding="utf-8")
    result = verify_dist(dist, run=False)
    assert result["ok"] is True
    assert result["inside_dist"] is True


def test_verify_dist_run_reports_missing_exe(tmp_path):
    dist = _fake_dist(tmp_path, exe=False)
    result = verify_dist(dist, exe_name=CLI_EXE_NAME, run=True)
    assert result["ok"] is False
    assert any("可执行文件不存在" in p for p in result["problems"])


def test_verify_dist_live_path_on_fake_exe_fails_loudly(tmp_path):
    """假 exe（非真产物）必须**判未通过**——校验不得对"跑不起来"睁一只眼。"""
    dist = _fake_dist(tmp_path)
    result = verify_dist(dist, exe_name=CLI_EXE_NAME, run=True, timeout=30)
    assert result["ok"] is False
    assert result["problems"], "假 exe 应产生问题清单（空清单 = 空验）"


# ------------------------------------------------------------------ 验伪：inside_dist 判定
def test_inside_dist_detects_repo_data_outside_dist(tmp_path):
    """核心验伪：冻结态若解析到 **dist 之外** 的数据目录（如仓库 data/），必须判失败。

    这里用"数据目录在 dist 外"直接检验 :func:`verify_dist` 的判定逻辑：
    造假一个"数据在 dist 外但存在"的布局，断言 inside_dist=False。
    """
    from labelcheck.packaging import _is_within

    outside = tmp_path / "repo" / "data"
    outside.mkdir(parents=True)
    dist = tmp_path / "dist"
    dist.mkdir()
    assert _is_within(outside, dist) is False, "dist 之外的数据目录不得判为 inside"
    assert _is_within(dist / "data", dist) is True


def test_neutral_env_strips_data_dir_var():
    env = neutral_env({ENV_VAR: "/somewhere", "OTHER": "1"})
    assert ENV_VAR not in env
    assert env["OTHER"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_exe_names_are_distinct():
    assert GUI_EXE_NAME != CLI_EXE_NAME


# ------------------------------------------------------------------ 冻结态实跑（真 exe，无则跳过）
def _dist_available():
    """仓库是否已构建 dist（构建产物不入仓；CI 不构建 → 跳过实跑用例）。"""
    from labelcheck.packaging import default_dist_dir

    return (default_dist_dir() / "labelcheck" / "labelcheck.exe").is_file()


@pytest.mark.skipif(not _dist_available(), reason="未构建 dist（跑 tools/build_exe.py 后生效）")
def test_verify_dist_live_cli_exe_passes():
    """真实 CLI exe：冻结态实跑必须通过（frozen + inside_dist + 规则数 > 0）。"""
    from labelcheck.packaging import CLI_EXE_NAME, default_dist_dir

    result = verify_dist(default_dist_dir() / "labelcheck", exe_name=CLI_EXE_NAME, run=True)
    assert result["ok"], result["problems"]
    assert result["frozen"] is True
    assert result["inside_dist"] is True
    assert result["verified_rule_count"] > 0


@pytest.mark.skipif(not _dist_available(), reason="未构建 dist（跑 tools/build_exe.py 后生效）")
def test_verify_dist_live_gui_exe_passes_via_selftest():
    """真实 GUI exe（窗口版）：--selftest 写文件方式必须通过。"""
    from labelcheck.packaging import GUI_EXE_NAME, default_dist_dir

    result = verify_dist(
        default_dist_dir() / "labelcheck-gui", exe_name=GUI_EXE_NAME, run=True,
        gui_selftest=True)
    assert result["ok"], result["problems"]
    assert result["frozen"] is True
    assert result["inside_dist"] is True
    assert result["verified_rule_count"] > 0
