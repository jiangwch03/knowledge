from langchain_text_splitters import RecursiveCharacterTextSplitter

from knowledge_common.utils.snowflake_util import SnowflakeUtil
from knowledge_content.splitter.base import BaseDocumentSplitter
from knowledge_content.splitter.vo import TextSegmentMetadataVo, TextSegmentVo


class FixedLengthTextSplitter(BaseDocumentSplitter):
    """按固定长度切分：先用 RecursiveCharacterTextSplitter，明显超长再按字符硬切。"""

    # 超长容差：超过 chunk_size 的 25% 才二次硬切
    _SOFT_OVERFLOW_RATIO = 0.25

    def __init__(self, *, chunk_size: int, overlap: int) -> None:
        self.chunk_size = chunk_size  # 分块目标长度（字符数）
        self.overlap = overlap  # 相邻分块重叠长度
        self._soft_limit = int(chunk_size * (1 + self._SOFT_OVERFLOW_RATIO))
        # 优先按段落/换行/空格等自然边界递归切分
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,  # 分块最大长度（字符数）
            chunk_overlap=overlap,  # 相邻分块重叠长度
            length_function=len,  # 按字符数计量长度
        )

    def split(self, text: str) -> list[TextSegmentVo]:
        """切分文本；轻微超长保留，明显超过 soft_limit 才二次硬切。"""
        if not text:
            return []

        chunks: list[str] = self._splitter.split_text(text)
        # RecursiveCharacterTextSplitter 可能产出超长块；仅明显超限时硬切
        segments: list[TextSegmentVo] = []
        for chunk in chunks:
            if not chunk:
                continue
            if len(chunk) <= self._soft_limit:
                segments.append(self._to_segment(chunk))
            else:
                segments.extend(self._split_by_character(chunk))
        return segments

    def _split_by_character(self, text: str) -> list[TextSegmentVo]:
        """按字符硬切，步进为 chunk_size - overlap，确保块长不超过 chunk_size。"""
        segments: list[TextSegmentVo] = []
        start: int = 0
        text_len: int = len(text)
        while start < text_len:
            end: int = min(start + self.chunk_size, text_len)
            part: str = text[start:end]
            if part:
                segments.append(self._to_segment(part))
            if end >= text_len:
                break
            # 下一块起点回退 overlap，保持相邻块重叠
            start = end - min(self.overlap, end)
        return segments

    def _to_segment(self, text: str) -> TextSegmentVo:
        """封装为 TextSegmentVo，生成唯一 chunk_id 并同步写入 metadata。"""
        chunk_id: str = SnowflakeUtil.next_id()
        return TextSegmentVo(
            text=text,
            metadata=TextSegmentMetadataVo(chunk_id=chunk_id),
            chunk_id=chunk_id,
        )
