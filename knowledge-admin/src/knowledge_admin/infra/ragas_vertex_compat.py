"""让 RAGAS 能在 langchain-community 0.4 上导入。

RAGAS 0.4.3 加载时会执行
``from langchain_community.chat_models.vertexai import ChatVertexAI``。
社区包 0.4 已去掉这个模块。测评只用 OpenAI 兼容的对话模型，不会实例化 Vertex。
"""

from __future__ import annotations

import sys
import types


def ensure_ragas_vertex_chat() -> None:
    """缺模块时补一个不会被调用的 ChatVertexAI，已有真实模块则不动。"""
    module_name = 'langchain_community.chat_models.vertexai'
    if module_name in sys.modules:
        return
    try:
        __import__(module_name)
    except ModuleNotFoundError:
        module = types.ModuleType(module_name)

        class ChatVertexAI:
            """占位。当前测评不使用 Google Vertex。"""

        module.ChatVertexAI = ChatVertexAI
        sys.modules[module_name] = module
