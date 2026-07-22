from __future__ import annotations

import struct


def pack_embedding_vector(vector: list[float]) -> bytes:
    """float32 little-endian 打包，供 knowledge_document_segment.embedding_vector 落库。"""
    return struct.pack(f'<{len(vector)}f', *vector)


def unpack_embedding_vector(payload: bytes | memoryview | None) -> list[float]:
    """从 MEDIUMBLOB 还原 float32 向量。"""
    if not payload:
        return []
    data = bytes(payload)
    if len(data) % 4 != 0:
        raise ValueError(f'embedding_vector 长度非法: {len(data)}')
    n: int = len(data) // 4
    return list(struct.unpack(f'<{n}f', data))
