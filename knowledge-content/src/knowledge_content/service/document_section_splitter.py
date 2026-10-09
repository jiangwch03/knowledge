"""把上传文档的 Markdown 切成出题用的节。不按向量块大小再切。"""
from __future__ import annotations

import re

from knowledge_common.facade.api.knowledge_content.document_section_vo import DocumentSectionVo

_HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$')
_FENCE_PATTERN = re.compile(r'^\s*(```+|~~~+)')
_SECTION_CHARS = 8000
_MIN_BREAK = 6000


class DocumentSectionSplitter:
    """按标题切节。没有标题时大约每 8000 字一节。"""

    @classmethod
    def split(cls, text: str) -> list[DocumentSectionVo]:
        # 步骤1：有标题就按标题切；代码围栏里的 # 不当标题
        headed = cls._split_by_headings(text)
        if headed is not None:
            return headed
        # 步骤2：整篇没有标题，按字数切开，标题和上级标题留空
        return cls._split_by_chars(text)

    @classmethod
    def _split_by_headings(cls, text: str) -> list[DocumentSectionVo] | None:
        header_stack: list[tuple[int, str]] = []
        current_title = ''
        current_parent = ''
        current_lines: list[str] = []
        saw_heading = False
        in_fence = False
        drafts: list[tuple[str, str, list[str]]] = []

        def flush() -> None:
            if not current_lines:
                return
            drafts.append((current_title, current_parent, list(current_lines)))

        for line in text.splitlines():
            if cls._is_fence_line(line):
                in_fence = not in_fence
                current_lines.append(line)
                continue
            if in_fence:
                current_lines.append(line)
                continue
            header = cls._parse_header(line)
            if header is None:
                current_lines.append(line)
                continue
            flush()
            saw_heading = True
            current_lines = [line]
            level, title = header
            current_parent = cls._parent_title(header_stack, level)
            current_title = title
            cls._push_header(header_stack, level, title)
        flush()
        if not saw_heading:
            return None
        return cls._to_sections(drafts)

    @classmethod
    def _split_by_chars(cls, text: str) -> list[DocumentSectionVo]:
        stripped = text.strip()
        if not stripped:
            return []
        sections: list[DocumentSectionVo] = []
        start = 0
        length = len(stripped)
        while start < length:
            end = min(start + _SECTION_CHARS, length)
            if end < length and end - start > _MIN_BREAK:
                break_at = stripped.rfind('\n\n', start + _MIN_BREAK, end)
                if break_at != -1:
                    end = break_at
            chunk = stripped[start:end].strip()
            if chunk:
                sections.append(
                    DocumentSectionVo(
                        section_order=len(sections),
                        title='',
                        parent_title='',
                        body=chunk,
                    )
                )
            if end >= length:
                break
            start = end
            while start < length and stripped[start] == '\n':
                start += 1
        return sections

    @staticmethod
    def _to_sections(drafts: list[tuple[str, str, list[str]]]) -> list[DocumentSectionVo]:
        sections: list[DocumentSectionVo] = []
        for title, parent, lines in drafts:
            body = '\n'.join(lines).strip()
            if not body:
                continue
            sections.append(
                DocumentSectionVo(
                    section_order=len(sections),
                    title=title,
                    parent_title=parent,
                    body=body,
                )
            )
        return sections

    @staticmethod
    def _is_fence_line(line: str) -> bool:
        return bool(_FENCE_PATTERN.match(line))

    @staticmethod
    def _parse_header(line: str) -> tuple[int, str] | None:
        match = _HEADER_PATTERN.match(line)
        if match is None:
            return None
        return len(match.group(1)), match.group(2).strip()

    @staticmethod
    def _parent_title(header_stack: list[tuple[int, str]], level: int) -> str:
        for stacked_level, stacked_title in reversed(header_stack):
            if stacked_level < level:
                return stacked_title
        return ''

    @staticmethod
    def _push_header(header_stack: list[tuple[int, str]], level: int, title: str) -> None:
        while header_stack and header_stack[-1][0] >= level:
            header_stack.pop()
        header_stack.append((level, title))
