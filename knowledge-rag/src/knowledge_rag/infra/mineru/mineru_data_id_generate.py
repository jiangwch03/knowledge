"""MinerU data_id 生成与校验工具

data_id 规则：
- 由大小写英文字母、数字、下划线（_）、短划线（-）、英文句号（.）组成
- 不超过 128 个字符
- 可用于唯一标识业务数据
"""

import re
import uuid

from knowledge_common.exceptions.exception import ServiceException

# data_id 允许字符的正则表达式
_DATA_ID_PATTERN = re.compile(r'^[A-Za-z0-9_.-]+$')


def generate_data_id() -> str:
    """生成一个符合 MinerU 规范的 data_id。

    使用 UUID4 生成全局唯一标识符，字符集仅包含大小写英文字母、
    数字和短划线（-），长度固定为 36 个字符，满足不超过 128 字符的限制。

    Returns:
        str: 新生成的 data_id，例如 "550e8400-e29b-41d4-a716-446655440000"。
    """
    return str(uuid.uuid4())


def generate_data_id_with_prefix(prefix: str) -> str:
    """基于指定前缀生成 data_id。

    前缀与 UUID 之间使用下划线（_）连接，便于业务分类识别。
    生成的 data_id 总长度不超过 128 个字符。

    Args:
        prefix: 业务前缀，只能包含大小写英文字母、数字、下划线（_）、
                短划线（-）、英文句号（.）。

    Returns:
        str: 带前缀的 data_id，例如 "doc_550e8400-e29b-41d4-a716-446655440000"。

    Raises:
        ValueError: 前缀包含非法字符或总长度超过 128 个字符。
    """
    if not prefix:
        raise ServiceException('前缀不能为空')
    if not _DATA_ID_PATTERN.match(prefix):
        raise ServiceException(
            '前缀只能包含大小写英文字母、数字、下划线（_）、短划线（-）、英文句号（.）'
        )
    if len(prefix) > 92:
        raise ServiceException(f'data_id前缀长度 {len(prefix)} 超过最大限制 92')
    suffix = generate_data_id()
    data_id = f'{prefix}_{suffix}'

    if len(data_id) > 128:
        raise ServiceException(f'生成的 data_id 长度 {len(data_id)} 超过最大限制 128')

    return data_id


def generate_split_data_id(base_data_id: str, part_index: int, page_start: int, page_end: int) -> str:
    """基于基础 data_id 生成文档拆分后的 chunk data_id。

    格式: {base_data_id}_part{part_index}_p{page_start}-{page_end}
    总长度不超过 128 个字符，字符集符合 MinerU 规范。

    Args:
        base_data_id: 基础 data_id（通常为 UUID）。
        part_index: 拆分块序号（从 1 开始）。
        page_start: 页码范围起始页。
        page_end: 页码范围结束页。

    Returns:
        str: 拆分后的 data_id。

    Raises:
        ServiceException: base_data_id 非法或生成的 data_id 超过 128 字符。
    """
    if not base_data_id or not _DATA_ID_PATTERN.match(base_data_id):
        raise ServiceException(
            f'base_data_id 只能包含大小写英文字母、数字、下划线（_）、短划线（-）、英文句号（.），'
            f'当前值: {base_data_id}'
        )

    suffix = f'part{part_index}_p{page_start}-{page_end}'
    data_id = f'{base_data_id}_{suffix}'

    if len(data_id) > 128:
        raise ServiceException(f'生成的 data_id 长度 {len(data_id)} 超过最大限制 128')

    return data_id


def validate_data_id(data_id: str) -> bool:
    """校验 data_id 是否符合 MinerU 规范。

    Args:
        data_id: 待校验的业务数据 ID。

    Returns:
        bool: 符合规范返回 True，否则返回 False。
    """
    if not data_id or len(data_id) > 128:
        return False
    return bool(_DATA_ID_PATTERN.match(data_id))
