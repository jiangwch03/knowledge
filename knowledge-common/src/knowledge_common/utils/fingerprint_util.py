"""
指纹计算工具

对任意可 JSON 序列化的负载、或原始字节做稳定 SHA-256 指纹。
与具体业务域无关，业务侧自行组装 payload 后调用 of / of_bytes。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class FingerprintUtil:
    """内容指纹工具（SHA-256 + 规范化 JSON）"""

    @classmethod
    def of(cls, value: Any) -> str:
        """
        对任意可序列化对象计算内容指纹。

        :param value: dict / list / 基础类型等
        :return: SHA-256 hex
        """
        return cls._sha256_hex(cls._canonical_json(value))

    @classmethod
    def of_bytes(cls, data: str | bytes) -> str:
        """
        对原始字节/字符串计算指纹（文件、正文等）。

        :param data: 字符串（按 utf-8）或 bytes
        :return: 64 位小写 hex
        """
        return cls._sha256_hex(data)

    @classmethod
    def _sha256_hex(cls, data: str | bytes) -> str:
        if isinstance(data, str):
            data = data.encode('utf-8')
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def _canonical_json(cls, value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            default=str,
        )
