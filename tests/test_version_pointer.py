# -*- coding: utf-8 -*-
"""README 版本指针守门（SI-048）。

背景（2026-10-25 实测）：`v0.2.0` 的 tag 树里 README `:149` 仍写

    不想装 Python？直接下 **[Release v0.1.0](.../releases/tag/v0.1.0)**：
    | `labelcheck-gui-v0.1.0-win64.zip` | ...

而 `v0.2.0` 的 Release 实际附件是 `labelcheck-gui-v0.2.0-win64.zip` /
`labelcheck-cli-v0.2.0-win64.zip`。用户照「下载即用」那一节走，拿到的是 **v0.1.0 的 exe**。

★ 这一条正是「presence 判据」的已知漏项：同一份 tag 树 `:9` 写着
「✅ v0.2.0 已发布」，所以「README 里出现过自身版本号」这个判据判它绿 ——
但真正决定用户下到哪一版的**下载节**指向旧版。故本门只认**下载节里的指针**，
不做全文存在性判断。

判据：
  ① 「下载即用」节里的 Release 链接 tag == 当前版本；
  ② 同一节附件表里的 zip 文件名版本 == 当前版本（`labelcheck-*-vX.Y.Z-win64.zip`）；
  ③ 负控：喂旧版本文本，①② 必须报错；且「只出现版本号但下载节指向旧版」的
     反例必须被判红（这条直接把 presence 判据的失效形态钉成回归测试）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"

ASSET = re.compile(r"labelcheck-(?:gui|cli)-v(\d+\.\d+\.\d+)-win64\.zip")


def _version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, "pyproject.toml 里找不到 project.version"
    return m.group(1)


def _download_section(readme: str) -> str:
    """「下载即用」节：从该标题行起，到下一个 `## ` 标题为止。"""
    lines = readme.splitlines()
    out, started = [], False
    for line in lines:
        if line.startswith("## ") and "下载" in line:
            started = True
            continue
        if started:
            if line.startswith("## "):
                break
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------- 审计函数

def audit_download_release_link(readme: str, version: str) -> list[str]:
    """① 下载节里的 Release 链接版本。"""
    section = _download_section(readme)
    if not section:
        return ["README 找不到「下载即用」节 —— 该节被删或改名"]
    found = re.findall(r"releases/tag/v(\d+\.\d+\.\d+)", section)
    if not found:
        return ["「下载即用」节里找不到 releases/tag/vX.Y.Z 链接"]
    # 「上一版 … 仍在」这类历史链接允许并存，但至少一条必须指向当前版本；
    # 且**第一条**（主下载入口）必须指向当前版本。
    problems = []
    if found[0] != version:
        problems.append(
            "「下载即用」节的主下载链接 = v{0}，期望 v{1}".format(found[0], version)
        )
    if version not in found:
        problems.append(
            "「下载即用」节里没有一条链接指向 v{0}（实测：{1}）".format(
                version, sorted(set(found))
            )
        )
    return problems


def audit_asset_names(readme: str, version: str) -> list[str]:
    """② 下载节附件表的 zip 文件名版本。"""
    section = _download_section(readme)
    if not section:
        return ["README 找不到「下载即用」节 —— 该节被删或改名"]
    names = ASSET.findall(section)
    if not names:
        return ["「下载即用」节里找不到 labelcheck-*-vX.Y.Z-win64.zip 附件名"]
    return [
        "「下载即用」节附件名 = labelcheck-*-v{0}-win64.zip，期望 v{1}".format(v, version)
        for v in names
        if v != version
    ]


# ---------------------------------------------------------------- 真文件断言

def test_download_section_release_link_matches_version():
    """① —— 主下载链接必须指向当前版本。"""
    problems = audit_download_release_link(README.read_text(encoding="utf-8"), _version())
    assert problems == [], "\n".join(problems)


def test_download_section_asset_names_match_version():
    """② —— 附件 zip 名必须等于当前版本。"""
    problems = audit_asset_names(README.read_text(encoding="utf-8"), _version())
    assert problems == [], "\n".join(problems)


# ---------------------------------------------------------------- ③ 负控

def test_negative_control_release_link_detects_stale():
    stale = (
        "## 下载即用（免安装）\n\n"
        "不想装 Python？直接下 **[Release v0.9.8](https://x/releases/tag/v0.9.8)**：\n"
    )
    assert audit_download_release_link(stale, "0.9.9") != []
    assert audit_download_release_link(stale.replace("0.9.8", "0.9.9"), "0.9.9") == []


def test_negative_control_asset_names_detect_stale():
    stale = (
        "## 下载即用（免安装）\n"
        "| `labelcheck-gui-v0.9.8-win64.zip` | 窗口版 |\n"
    )
    assert audit_asset_names(stale, "0.9.9") != []
    assert audit_asset_names(stale.replace("0.9.8", "0.9.9"), "0.9.9") == []


def test_negative_control_presence_is_not_correctness():
    """★ 把 presence 判据的失效形态钉成回归测试。

    这份合成本文**出现过** v0.9.9（状态行），但下载节指向 v0.9.8 ——
    「README 含自身版本号」会判绿，本门的两条判据必须判红。
    """
    text = (
        "> 状态：✅ **v0.9.9 已发布（2026-01-01）**——Release 挂双 exe zip\n\n"
        "## 下载即用（免安装）\n\n"
        "不想装 Python？直接下 **[Release v0.9.8](https://x/releases/tag/v0.9.8)**：\n"
        "| `labelcheck-gui-v0.9.8-win64.zip` | 窗口版 |\n"
    )
    assert "0.9.9" in text, "前提：本文确实出现了当前版本号（presence 会判绿）"
    assert audit_download_release_link(text, "0.9.9") != []
    assert audit_asset_names(text, "0.9.9") != []


def test_negative_control_missing_section_is_red():
    """删掉整节不能让门变绿。"""
    assert audit_download_release_link("无关内容", "0.9.9") != []
    assert audit_asset_names("无关内容", "0.9.9") != []
