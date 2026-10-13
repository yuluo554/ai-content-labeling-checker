# -*- coding: utf-8 -*-
"""批量扫描与两轮对账（FR-6 / FR-7，契约见 plan/04 §七）。

**定位**：把"单件核验"扩展到"一目录/一清单"——逐件走**同一条** ``engine.check_file``
分派（标识卡 JSON 与容器文件同一路径），产出可导出的 :class:`ScanResult`，
并支持两轮结果对账（新增违规 / 已修复 / 持续违规）。

**失败隔离（NFR-8）**：单件异常（坏 JSON、非法卡、不可解析容器、读盘失败……）**不得**
中断整批——该件记一条 ``status="unknown"`` 的失败记录（原因码 ``scan_error``）后继续。

**确定性（NFR-3）**：逐件产出无时钟/随机；进度行只写 stderr；``ScanResult`` 的
``to_dict`` 顺序固定（件序 = 输入发现序）→ 相同输入两次扫描逐字节一致。

**对账主键口径（M3 定夺，plan/06 D28）**——HANDOFF-M3 §三.2 提出的必答项：

M2 起解析通路的 ``card_id`` 由**内容哈希派生**（``PARSED-<16 hex>``），内容一变 id
就变——若一律按 ``card_id`` 对账，"同一文件被改动"会被误判成"新增 + 消失"，且
**"已修复"永远检不出来**（修复 = 内容变了 = id 变了）。故本模块为每件定一个
**稳定身份键**（:attr:`ScanItem.identity`），两轮据此配对：

- **标识卡 JSON 件** → ``card:<card_id>``：``card_id`` 是人工/上游赋予的**逻辑身份**，
  与文件名无关、与内容编辑无关（改文件名或改内容都不换身份）；
- **解析容器件 / 失败件** → ``file:<相对路径>``：容器件的 ``card_id`` 由内容派生、
  不稳定，改按**相对路径**配对（路径稳定；容器内容被改动正是我们要追踪的"修复/回归"）。

``content_sha256`` **不参与配对**，只用于独立检测"内容是否变动"（``content_changed``）
——这样"内容改了但身份不变"会被如实标出，而不会退化成"新增 + 消失"。
"""

from .diff import (
    STATUS_ADDED, STATUS_CONTENT_CHANGED, STATUS_FIXED, STATUS_NEW, STATUS_PERSISTENT,
    STATUS_REMOVED, STATUS_STABLE, DiffEntry, DiffResult, diff_scans,
)
from .scanner import (
    CODE_CONTAINER_TOO_LARGE, CODE_SCAN_ERROR, KIND_CARD, KIND_CONTAINER, KIND_FAILED,
    ScanItem, ScanResult, iter_input_paths, scan_paths, scan_target,
)

__all__ = [
    "scan_paths", "scan_target", "iter_input_paths", "ScanItem", "ScanResult",
    "KIND_CARD", "KIND_CONTAINER", "KIND_FAILED", "CODE_SCAN_ERROR",
    "CODE_CONTAINER_TOO_LARGE",
    "diff_scans", "DiffResult", "DiffEntry",
    "STATUS_ADDED", "STATUS_FIXED", "STATUS_PERSISTENT", "STATUS_STABLE",
    "STATUS_NEW", "STATUS_REMOVED", "STATUS_CONTENT_CHANGED",
]