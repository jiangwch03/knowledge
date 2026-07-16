import json


def format_sse(event: str, data: dict) -> str:
    """格式化 SSE 事件字符串。"""
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'
