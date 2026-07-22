import re

from knowledge_common.utils.snowflake_util import SnowflakeUtil
from knowledge_content.splitter.base import BaseDocumentSplitter
from knowledge_content.splitter.vo import TextSegmentMetadataVo, TextSegmentVo


class RegexTextSplitter(BaseDocumentSplitter):
    """按正则分隔符切分文本，再合并/硬切到 chunk_size 以内。

    处理流程：
      1. 用 pattern 做 re.split，得到若干碎片（分隔符本身会被丢掉）
      2. 贪心合并碎片：尽量拼到接近但不超过 chunk_size
      3. 仍超长的块再按 chunk_size / overlap 字符硬切
    """

    def __init__(self, *, pattern: str, chunk_size: int, overlap: int) -> None:
        # 用于切分的正则表达式。
        # re.split 会在匹配处断开，匹配到的分隔符本身不会进入结果。
        # 例："\\n\\n+" 按空行切；"[。！？]" 按句号等标点切。
        self.pattern = pattern

        # 单个 chunk 的目标最大字符数。
        # 合并阶段尽量凑到不超过该长度；仍超长则进入硬切。
        self.chunk_size = chunk_size

        # 相邻硬切子块的重叠字符数，仅在 _split_oversize 时生效。
        # 例：chunk_size=500, overlap=50 → 下一块起点 = 上一块终点 - 50。
        self.overlap = overlap

        self._compiled = re.compile(pattern)

    def split(self, text: str) -> list[TextSegmentVo]:
        """切分入口：正则拆分 → 合并到 chunk_size → 超长再硬切。"""
        if not text:
            return []

        # 按正则切开，过滤空串（连续分隔符会产生空串）
        parts: list[str] = [part for part in self._compiled.split(text) if part]
        # 把过碎的片段拼回接近 chunk_size 的块
        merged: list[str] = self._merge_parts(parts)
        segments: list[TextSegmentVo] = []
        for part in merged:
            if len(part) <= self.chunk_size:
                segments.append(self._to_segment(part))
            else:
                # 单个 part 本身就超过 chunk_size（正则切点太稀），只能硬切
                segments.extend(self._split_oversize(part))
        return segments

    def _merge_parts(self, parts: list[str]) -> list[str]:
        """贪心合并：能拼进当前块就拼，拼不下就开新块。

        目标是减少过碎 chunk，同时保证合并后长度不超过 chunk_size。
        注意：若某个 part 单独就已超过 chunk_size，会原样保留，交给后续硬切。
        """
        if not parts:
            return []

        merged: list[str] = []
        current: str = parts[0]
        for part in parts[1:]:
            if len(current) + len(part) <= self.chunk_size:
                current += part
            else:
                merged.append(current)
                current = part
        merged.append(current)
        return merged

    def _split_oversize(self, text: str) -> list[TextSegmentVo]:
        """按字符硬切超长文本，步进为 chunk_size - overlap。"""
        chunks: list[str] = []
        start: int = 0
        text_len: int = len(text)
        while start < text_len:
            end: int = min(start + self.chunk_size, text_len)
            chunks.append(text[start:end])
            if end >= text_len:
                break
            # 下一块起点回退 overlap，保持相邻块重叠上下文
            start = end - min(self.overlap, end)
        return [self._to_segment(chunk) for chunk in chunks if chunk]

    def _to_segment(self, text: str) -> TextSegmentVo:
        """封装为 TextSegmentVo，生成唯一 chunk_id 并同步写入 metadata。"""
        chunk_id: str = SnowflakeUtil.next_id()
        return TextSegmentVo(
            text=text,
            metadata=TextSegmentMetadataVo(chunk_id=chunk_id),
            chunk_id=chunk_id,
        )
