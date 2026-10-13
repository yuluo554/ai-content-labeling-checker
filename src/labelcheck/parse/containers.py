# -*- coding: utf-8 -*-
"""容器元数据抽取（纯 stdlib、字节级、**确定性**）。

职责边界（plan/04 §四.1 / plan/06 P2）：只做**结构解析**——把可解析载体
（PNG / JPEG / ISO BMFF 即 MP4·M4A）中承载元数据的字节块取出，交给
:mod:`labelcheck.parse.aigc` 找 AIGC JSON 载荷。**不解析图像/音频信号**，
不做任何水印检测或标识规避（明确非目标）。

**显式降级纪律**：结构截断/畸形 → 返回 ``structure_ok=False``，解析结果据此把
隐式作用域标为"未观测"，引擎对所有规则判 ``unknown``（**绝不臆测**）。
"""

import struct
import zlib

#: 单块元数据上限（防超大容器吃内存；元数据块远小于此，媒体数据在 mdat 里被跳过）
MAX_BLOB = 4 * 1024 * 1024

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SOI = b"\xff\xd8"

CONTAINER_PNG = "png"
CONTAINER_JPEG = "jpeg"
CONTAINER_ISO = "iso-bmff"

#: 文件后缀 → 容器类型（CLI 自动分派的唯一依据）
SUFFIX_TO_CONTAINER = {
    ".png": CONTAINER_PNG,
    ".jpg": CONTAINER_JPEG,
    ".jpeg": CONTAINER_JPEG,
    ".mp4": CONTAINER_ISO,
    ".m4a": CONTAINER_ISO,
    ".m4v": CONTAINER_ISO,
    ".mov": CONTAINER_ISO,
}

#: ISO BMFF 中承载元数据的顶层 box（媒体数据 ``mdat`` 按尺寸跳过，天然避开）
_ISO_METADATA_BOXES = (b"moov", b"uuid", b"meta")


def detect_container(data):
    """按文件头魔数识别容器类型；无法识别返回 ``None``。"""
    if not data:
        return None
    if data.startswith(PNG_SIGNATURE):
        return CONTAINER_PNG
    if data.startswith(JPEG_SOI):
        return CONTAINER_JPEG
    # ISO BMFF：偏移 4 起的 4 字节为 ``ftyp``
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return CONTAINER_ISO
    return None


def iso_carrier(data):
    """ISO BMFF 的 major brand → 载体（``audio``/``video``）。

    M4A/M4B 主品牌为音频；其余（isom/mp42/avc1…）按视频处理。
    """
    if len(data) >= 12:
        brand = data[8:12]
        if brand[:3] in (b"M4A", b"M4B"):
            return "audio"
    return "video"


def _decode(blob):
    """字节块 → 文本（UTF-8 优先，失败退 latin-1；两者都不抛）。"""
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("latin-1")


def iter_metadata_blobs(data, container):
    """抽取容器的元数据文本块。

    :returns: ``(blobs, structure_ok)``——``blobs`` 为文本块列表（发现顺序，确定性）；
        ``structure_ok=False`` 表示容器结构截断/畸形（→ 隐式作用域视为未观测）。
    """
    if container == CONTAINER_PNG:
        return _png_blobs(data)
    if container == CONTAINER_JPEG:
        return _jpeg_blobs(data)
    if container == CONTAINER_ISO:
        return _iso_blobs(data)
    return [], False


# ------------------------------------------------------------------ PNG
def _png_blobs(data):
    blobs = []
    pos = len(PNG_SIGNATURE)
    total = len(data)
    while pos + 8 <= total:
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        payload_start = pos + 8
        payload_end = payload_start + length
        if payload_end + 4 > total:
            return blobs, False  # 截断（块体或 CRC 不完整）
        payload = data[payload_start:payload_end]
        text = _png_text(chunk_type, payload)
        if text is not None and len(text) <= MAX_BLOB:
            blobs.append(text)
        pos = payload_end + 4  # 跳过 CRC
        if chunk_type == b"IEND":
            return blobs, True
    # 走到这里说明块在边界处耗尽但**没见过 IEND**：PNG 必须以此块收尾，
    # 故即便恰好停在块边界，结构也不完整（截断在末尾整块上）。
    return blobs, False


def _png_text(chunk_type, payload):
    """从 tEXt / zTXt / iTXt 块取文本；其它块返回 None。"""
    try:
        if chunk_type == b"tEXt":
            _, text = payload.split(b"\x00", 1)
            return _decode(text)
        if chunk_type == b"zTXt":
            _, rest = payload.split(b"\x00", 1)
            return _decode(zlib.decompress(rest[1:]))  # rest[0] = 压缩方法
        if chunk_type == b"iTXt":
            _, rest = payload.split(b"\x00", 1)
            comp_flag = rest[0]
            # cflag(1) cmethod(1) lang\0 translated\0 text
            remainder = rest[2:]
            _, remainder = remainder.split(b"\x00", 1)  # 去 language tag
            _, text = remainder.split(b"\x00", 1)       # 去 translated keyword
            if comp_flag == 1:
                text = zlib.decompress(text)
            return _decode(text)
    except (ValueError, IndexError, zlib.error):
        return None
    return None


# ------------------------------------------------------------------ JPEG
def _jpeg_blobs(data):
    blobs = []
    pos = 2  # 跳过 SOI
    total = len(data)
    while pos + 1 < total:
        if data[pos] != 0xFF:
            pos += 1  # 容忍填充字节
            continue
        marker = data[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            pos += 2
            continue
        if marker == 0xDA:  # SOS：之后是压缩数据，元数据段已在前
            return blobs, True
        if marker == 0xD9:  # EOI
            return blobs, True
        if pos + 4 > total:
            return blobs, False
        seg_len = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        if seg_len < 2 or pos + 2 + seg_len > total:
            return blobs, False
        segment = data[pos + 4:pos + 2 + seg_len]
        if marker in (0xE1, 0xED, 0xFE) and len(segment) <= MAX_BLOB:
            blobs.append(_decode(segment))
        pos += 2 + seg_len
    # 没走到 SOS/EOI 就耗尽 = 与 PNG 同理：结构不完整（截断）。
    return blobs, False


# ------------------------------------------------------------------ ISO BMFF（MP4 / M4A）
def _iso_blobs(data):
    blobs = []
    pos = 0
    total = len(data)
    saw_moov = False
    while pos + 8 <= total:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        box_type = data[pos + 4:pos + 8]
        header = 8
        if size == 1:  # 64 位长度
            if pos + 16 > total:
                return blobs, False
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:  # 至文件末尾
            size = total - pos
        if size < header or pos + size > total:
            return blobs, False
        if box_type == b"moov":
            saw_moov = True
        if box_type in _ISO_METADATA_BOXES:
            payload = data[pos + header:pos + size]
            if len(payload) <= MAX_BLOB:
                blobs.append(_decode(payload))
        pos += size
    # 结构完整 = 恰好走完所有 box **且**见过 moov（元数据容器；没有它就没有标签可查）
    return blobs, pos == total and saw_moov


__all__ = [
    "detect_container", "iso_carrier", "iter_metadata_blobs", "SUFFIX_TO_CONTAINER",
    "CONTAINER_PNG", "CONTAINER_JPEG", "CONTAINER_ISO", "MAX_BLOB",
]
