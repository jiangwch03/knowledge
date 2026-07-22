import re
from dataclasses import dataclass, field

from knowledge_common.utils.snowflake_util import SnowflakeUtil
from knowledge_content.splitter.base import BaseDocumentSplitter
from knowledge_content.splitter.vo import TextSegmentMetadataVo, TextSegmentVo

# 标题层级与 metadata 字段的一一对应：
#   # 标题        → title
#   ## 标题       → subtitle
#   ### 标题      → section
#   #### 标题     → subsection
#   ##### 标题    → subsubsection
#   ###### 标题   → subsubsubsection
_HEADER_METADATA_KEYS = (
    'title',
    'subtitle',
    'section',
    'subsection',
    'subsubsection',
    'subsubsubsection',
)
# 匹配 Markdown ATX 标题行，如 "# 产品说明"、"## 安装"
_HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$')
# 匹配代码围栏起止行（``` / ~~~），围栏内的 # 不当标题处理
_FENCE_PATTERN = re.compile(r'^\s*(```+|~~~+)')


@dataclass
class _RawSection:
    """按标题切出的原始段落，尚未做 chunk_size 二次切分。

    Attributes:
        text: 该标题下聚合后的正文（可能含标题行，取决于 strip_headers）。
        metadata: 当前标题路径对应的元数据（title/subtitle/...）。
    """

    text: str
    metadata: TextSegmentMetadataVo = field(default_factory=TextSegmentMetadataVo)


class MarkdownHeaderParentTextSplitter(BaseDocumentSplitter):
    """按 Markdown 标题切分文档，超长段落再按字符硬切，并保留父子 chunk 关系。

    处理流程：
      1. 按标题边界切成若干 section（带标题路径 metadata）
      2. 每个 section 若不超过 chunk_size，直接成为一个可向量化 chunk
      3. 若超过 chunk_size：生成父块（完整原文，不向量化）+ 多个带 overlap 的子块
    """

    def __init__(
        self,
        *,
        chunk_size: int,
        overlap: int,
        title_level: int = 6,
        return_each_line: bool = False,
        strip_headers: bool = False,
    ) -> None:
        # 单个 chunk 的目标最大字符数。
        # 标题切段后，若某段正文长度 <= chunk_size，整段作为一个 chunk；
        # 若超过，则再按 chunk_size 硬切成多个子块（并额外保留一个父块）。
        self.chunk_size = chunk_size

        # 相邻子块的重叠字符数，仅在「超长硬切」时生效。
        # 例：chunk_size=500, overlap=50 → 下一块起点 = 上一块终点 - 50，
        # 避免句子被拦腰切断后丢失上下文。
        self.overlap = overlap

        # 参与切分的最大标题层级（1~6）。
        # 例：title_level=2 时，只把 # / ## 当作切分段边界，
        # ### 及更低级标题当作普通正文，不会单独开新段。
        self.title_level = title_level

        # 标题切段后，段内正文如何组织：
        #   False（默认）：同一标题下的所有行聚合成一整段，再按 chunk_size 二次切分
        #   True：每一行单独作为一个 section（适合需要行级粒度的场景）
        self.return_each_line = return_each_line

        # 标题行是否写入正文 text：
        #   False（默认）：正文里保留标题行，如 "## 安装\n步骤一……"
        #   True：正文只含标题下的内容，标题信息只存在于 metadata
        self.strip_headers = strip_headers

    def split(self, text: str) -> list[TextSegmentVo]:
        """切分入口：先按标题切段，再对每段做 chunk_size 二次处理。

        Returns:
            TextSegmentVo 列表。超长段会包含 1 个父块（skip_embedding=True）
            + N 个子块（带 parent_chunk_id）。
        """
        sections: list[_RawSection] = self._parse_sections(text)
        segments: list[TextSegmentVo] = []
        for section in sections:
            if not section.text:
                continue
            segments.extend(
                self._split_by_chunk_size(section.text, section.metadata),
            )
        return segments

    def _parse_sections(self, text: str) -> list[_RawSection]:
        """按 return_each_line 选择解析策略。"""
        if self.return_each_line:
            return self._parse_line_sections(text)
        return self._parse_aggregated_sections(text)

    def _parse_aggregated_sections(self, text: str) -> list[_RawSection]:
        """按标题边界聚合正文（默认模式）。

        规则：
          - 遇到 <= title_level 的标题时，先把上一段 flush 出去，再开新段
          - 同一标题下的连续行合并为一段
          - 代码围栏（``` / ~~~）内不识别标题，避免代码示例里的 # 被误切
        """
        sections: list[_RawSection] = []
        # 当前标题路径栈，index 0 = 一级标题文本，index 1 = 二级……
        # 例：遇到 "# 产品" 再遇到 "## 安装" → ["产品", "安装"]
        header_stack: list[str] = []
        current_lines: list[str] = []
        current_metadata: TextSegmentMetadataVo = TextSegmentMetadataVo()
        in_fence: bool = False  # True 表示当前处于代码围栏内部

        def flush() -> None:
            """把 current_lines 刷成一个 _RawSection，并清空行缓冲。"""
            if not current_lines:
                return
            sections.append(
                _RawSection(
                    text='\n'.join(current_lines),
                    metadata=current_metadata.model_copy(),
                ),
            )

        for line in text.splitlines():
            # 围栏起止行：翻转 in_fence，行本身保留进正文
            if self._is_fence_line(line):
                in_fence = not in_fence
                current_lines.append(line)
                continue

            # 围栏内：一律当普通正文，不做标题识别
            if in_fence:
                current_lines.append(line)
                continue

            header: tuple[int, str] | None = self._parse_header(line)
            # header = (层级, 标题文本)，层级在 title_level 以内才作为切分段边界
            if header and header[0] <= self.title_level:
                # 先刷出上一段，再更新标题栈并开启新段
                flush()
                current_lines = []
                current_metadata = self._update_header_stack(
                    header_stack, header[0], header[1],
                )
                # strip_headers=False 时，标题行本身也写入新段正文
                if not self.strip_headers:
                    current_lines.append(line)
                continue

            # 普通正文行（或超过 title_level 的标题行）并入当前段
            current_lines.append(line)

        flush()  # 文件末尾最后一段
        return sections

    def _parse_line_sections(self, text: str) -> list[_RawSection]:
        """逐行切分模式（return_each_line=True）。

        每行各自成为一个 section；遇到标题时更新 header_stack / metadata，
        标题行是否保留由 strip_headers 决定。
        """
        sections: list[_RawSection] = []
        header_stack: list[str] = []
        in_fence: bool = False

        for line in text.splitlines():
            # 先按当前标题栈生成 metadata；若本行是标题，后面会再更新
            metadata: TextSegmentMetadataVo = self._metadata_from_stack(header_stack)

            if self._is_fence_line(line):
                in_fence = not in_fence
                sections.append(_RawSection(text=line, metadata=metadata))
                continue

            if in_fence:
                sections.append(_RawSection(text=line, metadata=metadata))
                continue

            header: tuple[int, str] | None = self._parse_header(line)
            if header and header[0] <= self.title_level:
                # 标题行：先更新栈，再决定是否把标题行本身输出为一段
                metadata = self._update_header_stack(
                    header_stack, header[0], header[1],
                )
                if not self.strip_headers:
                    sections.append(_RawSection(text=line, metadata=metadata))
                continue

            sections.append(_RawSection(text=line, metadata=metadata))

        return sections

    def _split_by_chunk_size(
        self,
        text: str,
        metadata: TextSegmentMetadataVo,
    ) -> list[TextSegmentVo]:
        """对单个 section 做长度控制，必要时建立父子 chunk。

        - 长度 <= chunk_size：直接返回 1 个可向量化 chunk
        - 长度 > chunk_size：
            1) 父块：完整原文，skip_embedding=True（不向量化，检索命中子块后可回查）
            2) 子块：按 chunk_size 滑动硬切，步进 = chunk_size - overlap，
               每个子块带 parent_chunk_id 指向父块
        """
        if len(text) <= self.chunk_size:
            chunk_id: str = SnowflakeUtil.next_id()
            return [
                TextSegmentVo(
                    text=text,
                    metadata=metadata.model_copy(update={'chunk_id': chunk_id}),
                    chunk_id=chunk_id,
                ),
            ]

        # ---- 超长：先生成父块 ----
        parent_chunk_id: str = SnowflakeUtil.next_id()
        segments: list[TextSegmentVo] = [
            TextSegmentVo(
                text=text,
                metadata=metadata.model_copy(
                    update={
                        'chunk_id': parent_chunk_id,
                        'skip_embedding': True,
                    },
                ),
                skip_embedding=True,
                chunk_id=parent_chunk_id,
            ),
        ]

        # ---- 再按 chunk_size / overlap 切子块 ----
        start: int = 0
        text_len: int = len(text)
        while start < text_len:
            end: int = min(start + self.chunk_size, text_len)
            child_chunk_id: str = SnowflakeUtil.next_id()
            segments.append(
                TextSegmentVo(
                    text=text[start:end],
                    metadata=metadata.model_copy(
                        update={
                            'chunk_id': child_chunk_id,
                            'parent_chunk_id': parent_chunk_id,
                        },
                    ),
                    parent_chunk_id=parent_chunk_id,
                    chunk_id=child_chunk_id,
                ),
            )
            if end >= text_len:
                break
            # 下一块起点回退 overlap，保证相邻子块有重叠上下文
            start = end - min(self.overlap, end)

        return segments

    def _is_fence_line(self, line: str) -> bool:
        """判断是否为代码围栏起止行（``` 或 ~~~）。"""
        return bool(_FENCE_PATTERN.match(line))

    def _parse_header(self, line: str) -> tuple[int, str] | None:
        """解析 ATX 标题行。

        Returns:
            (层级, 标题文本)，层级为 1~6；非标题行返回 None。
            例："## 安装" → (2, "安装")
        """
        match: re.Match[str] | None = _HEADER_PATTERN.match(line)
        if not match:
            return None
        return len(match.group(1)), match.group(2).strip()

    def _update_header_stack(
        self,
        header_stack: list[str],
        level: int,
        title: str,
    ) -> TextSegmentMetadataVo:
        """用新标题更新标题路径栈，并返回对应 metadata。

        规则：弹出同级及更深的标题，再压入当前标题。
        例：栈为 ["产品", "安装", "步骤"]，遇到 ## 配置 →
            弹出 "步骤"、"安装"，压入 "配置" → ["产品", "配置"]
        """
        while len(header_stack) >= level:
            header_stack.pop()
        header_stack.append(title)
        return self._metadata_from_stack(header_stack)

    def _metadata_from_stack(self, header_stack: list[str]) -> TextSegmentMetadataVo:
        """把标题栈映射为 TextSegmentMetadataVo 的 title/subtitle/... 字段。

        栈长度同时写入 header_level；未用到的层级字段置为 None。
        """
        values: dict[str, str | None] = {key: None for key in _HEADER_METADATA_KEYS}
        for index, title in enumerate(header_stack):
            values[_HEADER_METADATA_KEYS[index]] = title
        return TextSegmentMetadataVo(
            **values,
            header_level=len(header_stack) if header_stack else None,
        )
