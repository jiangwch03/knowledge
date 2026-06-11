"""
Redis 公共 JSON 序列化/反序列化模块

提取 redis_client 和 redis_pubsub_util 中重复的 JSON 处理逻辑，
提供统一的序列化/反序列化函数。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def serialize(value: Any) -> str:
    """
    序列化：Pydantic Model / dict / list / 基础类型 → JSON 字符串

    :param value: 待序列化的值
    :return: JSON 字符串
    """
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    return json.dumps(value, ensure_ascii=False, default=str)


def deserialize(raw: str | None, model: type | None = None) -> Any:
    """
    反序列化：JSON 字符串 → dict / Pydantic Model 实例

    :param raw: Redis 返回的原始字符串
    :param model: 目标 Pydantic 类型（可选）
    :return: 反序列化后的对象
    """
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # 非 JSON 格式直接返回原始字符串
        return raw
    if model is not None and isinstance(data, dict):
        return model.model_validate(data)
    return data


def encode_payload(payload: Any) -> str | bytes:
    """
    编码发布载荷

    - dict/list -> JSON 字符串
    - str/bytes -> 原样返回
    - 其他 -> str()

    :param payload: 待编码的载荷
    :return: 编码后的字符串
    """
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload
    return str(payload)


def decode_message_data(data: str | bytes | None) -> Any:
    """
    解码消息数据

    - bytes -> 尝试 JSON 反序列化，失败则 decode 为 str
    - str -> 尝试 JSON 反序列化，失败则原样返回
    - None -> 返回空字符串

    :param data: 待解码的数据
    :return: 解码后的数据
    """
    if data is None:
        return ''
    if isinstance(data, bytes):
        try:
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return data.decode('utf-8', errors='replace')
    # str
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return data
