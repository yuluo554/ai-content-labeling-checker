"""基础设施测试：RNG 金标准、JSON 确定性、数据目录定位四分支。"""

import json

import pytest

from labelcheck.errors import EnvironmentError_
from labelcheck.jsonio import (
    canonical_json, load_json, sha256_text, write_json, write_text_lf,
)
from labelcheck.paths import ENV_VAR, find_data_dir
from labelcheck.rng import GOLDEN_SEED0, SplitMix64, derive_seed

from _support import build_data_dir


# ------------------------------------------------------------------ RNG
def test_splitmix64_matches_golden_sequence():
    """splitmix64 对 seed=0 的前 8 项必须与金标准逐值相等（跨机器可复现的根基）。"""
    rng = SplitMix64(0)
    got = tuple(rng.next_u64() for _ in range(8))
    assert got == GOLDEN_SEED0


def test_splitmix64_is_reproducible():
    """同 seed 两次实例化必须产出完全相同的序列。"""
    a = SplitMix64(12345)
    b = SplitMix64(12345)
    assert [a.next_u64() for _ in range(16)] == [b.next_u64() for _ in range(16)]


def test_splitmix64_different_seeds_diverge():
    a = SplitMix64(1)
    b = SplitMix64(2)
    assert a.next_u64() != b.next_u64()


def test_splitmix64_randbelow_in_range_and_deterministic():
    rng = SplitMix64(7)
    values = [rng.randbelow(10) for _ in range(200)]
    assert all(0 <= v < 10 for v in values), "取值必须落在 [0, bound)"
    again = SplitMix64(7)
    assert [again.randbelow(10) for _ in range(200)] == values, "同 seed 序列必须一致"


def test_splitmix64_choice_and_shuffle_deterministic():
    items = ["a", "b", "c", "d"]
    rng1 = SplitMix64(99)
    rng2 = SplitMix64(99)
    assert [rng1.choice(items) for _ in range(20)] == [rng2.choice(items) for _ in range(20)]

    list1 = list(items)
    list2 = list(items)
    SplitMix64(5).shuffle(list1)
    SplitMix64(5).shuffle(list2)
    assert list1 == list2


def test_splitmix64_randbelow_rejects_nonpositive():
    with pytest.raises(ValueError):
        SplitMix64(1).randbelow(0)


def test_splitmix64_rejects_non_int_seed():
    with pytest.raises(TypeError):
        SplitMix64("42")


def test_derive_seed_deterministic_and_distinct():
    assert derive_seed(1, "text", 0) == derive_seed(1, "text", 0)
    assert derive_seed(1, "text", 0) != derive_seed(1, "image", 0)


# ------------------------------------------------------------------ JSON / 指纹
def test_sha256_text_matches_known_vector():
    # "abc" 的 sha256 是公开标准向量
    assert sha256_text("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_write_json_uses_lf_and_is_deterministic(tmp_path):
    path = tmp_path / "out.json"
    payload = {"b": 1, "a": "中文"}
    write_json(path, payload)
    write_json(tmp_path / "out2.json", payload)

    raw = path.read_bytes()
    assert b"\r\n" not in raw, "落盘必须用 LF（跨平台字节一致的前提）"
    assert raw == (tmp_path / "out2.json").read_bytes()
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_write_text_lf_no_cr(tmp_path):
    path = tmp_path / "x.txt"
    write_text_lf(path, "行一\n行二\n")
    assert b"\r" not in path.read_bytes()


def test_canonical_json_stable_for_same_object():
    obj = {"z": [1, 2], "a": {"k": "值"}}
    assert canonical_json(obj) == canonical_json(dict(obj))


def test_load_json_reports_missing_file_with_path():
    with pytest.raises(Exception) as excinfo:
        load_json("definitely-not-here.json")
    assert "不存在" in str(excinfo.value)


def test_load_json_rejects_bad_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json]", encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        load_json(path)
    assert "JSON 解析失败" in str(excinfo.value)


def test_load_json_decimal_mode(tmp_path):
    path = tmp_path / "num.json"
    path.write_text('{"v": 0.1}', encoding="utf-8")
    data = load_json(path, use_decimal=True)
    from decimal import Decimal
    assert data["v"] == Decimal("0.1")


# ------------------------------------------------------------------ 数据目录定位
def test_find_data_dir_explicit_wins(tmp_path):
    data = build_data_dir(tmp_path / "custom", {"d": {"status": "pending", "rules": []}})
    assert find_data_dir(explicit=data) == data.resolve()


def test_find_data_dir_env_var(tmp_path, monkeypatch):
    data = build_data_dir(tmp_path / "envdata", {"d": {"status": "pending", "rules": []}})
    monkeypatch.setenv(ENV_VAR, str(data))
    assert find_data_dir() == data.resolve()


def test_find_data_dir_explicit_beats_env(tmp_path, monkeypatch):
    explicit = build_data_dir(tmp_path / "explicit", {"d": {"status": "pending", "rules": []}})
    env = build_data_dir(tmp_path / "env", {"d": {"status": "pending", "rules": []}})
    monkeypatch.setenv(ENV_VAR, str(env))
    assert find_data_dir(explicit=explicit) == explicit.resolve()


def test_find_data_dir_missing_explicit_raises(tmp_path):
    with pytest.raises(EnvironmentError_):
        find_data_dir(explicit=tmp_path / "nope")


def test_find_data_dir_env_var_missing_dir_raises(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "nope"))
    with pytest.raises(EnvironmentError_):
        find_data_dir()


def test_find_data_dir_repo_default_is_repo_data(repo_root):
    """未指定时，源码态应从 __file__ 上溯定位到仓库 data/。"""
    resolved = find_data_dir()
    assert resolved == (repo_root / "data").resolve()


def test_find_data_dir_require_false_returns_none_when_nothing_found(tmp_path, monkeypatch):
    """定位失败且 require=False → 返回 None（供 version 等可降级命令使用）。"""
    import labelcheck.paths as paths_mod

    monkeypatch.delenv(ENV_VAR, raising=False)
    # 屏蔽仓库态与冻结态候选，模拟"什么都没有"的环境
    monkeypatch.setattr(paths_mod, "_frozen_candidates", lambda: [])
    monkeypatch.setattr(paths_mod, "_source_candidates", lambda: [])
    monkeypatch.setattr(paths_mod, "_cwd_candidates", lambda: [])

    assert find_data_dir(require=False) is None
    with pytest.raises(EnvironmentError_):
        find_data_dir(require=True)


def test_frozen_candidate_branch_used_when_meipass_set(tmp_path, monkeypatch):
    """PyInstaller 6 冻结态：sys._MEIPASS/data 必须优先于源码态。"""
    import sys

    frozen_data = build_data_dir(tmp_path / "meipass" / "data", {"d": {"status": "pending", "rules": []}})
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert find_data_dir() == frozen_data.resolve()


# ------------------------------------------------------------------ CI 编码门（v0.2.0）
def test_tools_entrypoints_use_utf8_stdio_guard():
    """输出中文的 tools 入口必须装 UTF-8 stdio 防护（CI 的 Windows runner 是 cp1252）。

    **为什么值得单测**：修前两处真实故障——``build_exe.py`` 在构建**开始前**、
    ``verify_package.py`` 在验收**全过之后**，都只因为一句中文 print 抛
    ``UnicodeEncodeError`` 而让 job 变红。本地 Git Bash 是 UTF-8，看不出来。
    这类缺陷只能靠"逐个入口检查"或真跑 CI 才能发现，故固化成门禁。
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    tools = root / "tools"
    #: 必须在中文输出的入口里调用防护（entry_* 只转发，cli.main 自带防护）
    required = ("build_exe.py", "verify_package.py")

    offenders = []
    for name in required:
        path = tools / name
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        called = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                fname = getattr(func, "id", None) or getattr(func, "attr", None)
                if fname == "ensure_utf8_stdio":
                    called = True
        if not called:
            offenders.append(name)
    assert not offenders, (
        "以下 tools 入口没有调用 ensure_utf8_stdio（CI cp1252 下中文输出会崩）："
        + "、".join(offenders))

    # 防护模块本身存在且不依赖第三方
    helper = tools / "_utf8_stdio.py"
    assert helper.is_file(), "缺少 tools/_utf8_stdio.py（共享防护实现）"
    assert "import sys" in helper.read_text(encoding="utf-8")
