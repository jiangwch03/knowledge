import re

from knowledge_common.exceptions.exception import ServiceException
from knowledge_content.enums.document_split_separator_dict_enum import DocumentSplitSeparatorDict
from knowledge_content.enums.split_type_enum import SplitType
from knowledge_content.splitter.base import BaseDocumentSplitter
from knowledge_content.splitter.fixed_length_splitter import FixedLengthTextSplitter
from knowledge_content.splitter.markdown_header_parent import MarkdownHeaderParentTextSplitter
from knowledge_content.splitter.regex_splitter import RegexTextSplitter
from knowledge_content.splitter.vo import DocumentSplitParamVo


class DocumentSplitterFactory:
    """按 split_type 创建对应文档切分器"""

    @staticmethod
    def get(param: DocumentSplitParamVo) -> BaseDocumentSplitter:
        # 标题切分：按 Markdown 标题层级聚合为父块
        if param.split_type == SplitType.TITLE:
            return MarkdownHeaderParentTextSplitter(
                chunk_size=param.chunk_size,
                overlap=param.overlap,
                title_level=param.title_level or 6,
                return_each_line=False,
                strip_headers=False,
            )
        # 智能切分：标题切分 + 行级返回，便于细粒度向量化
        if param.split_type == SplitType.SMART:
            return MarkdownHeaderParentTextSplitter(
                chunk_size=param.chunk_size,
                overlap=param.overlap,
                title_level=6,
                return_each_line=True,
                strip_headers=False,
            )
        # 固定长度切分：按固定字符长度滑动窗口切分
        if param.split_type == SplitType.LENGTH:
            return FixedLengthTextSplitter(
                chunk_size=param.chunk_size,
                overlap=param.overlap,
            )
        # 分隔符切分：按系统字典中的单个字面量分隔符切分（dict_value 支持 \\n 等可见转义）
        if param.split_type == SplitType.SEPARATOR:
            literal: str = DocumentSplitSeparatorDict.decode(param.separator or '')
            return RegexTextSplitter(
                pattern=re.escape(literal),  # 字面量，不做正则解释
                chunk_size=param.chunk_size,
                overlap=param.overlap,
            )
        # 正则切分：按自定义正则 pattern 切分
        if param.split_type == SplitType.REGEX:
            return RegexTextSplitter(
                pattern=param.regex or '',  # 切分正则；re.split 在匹配处断开，分隔符本身不保留
                chunk_size=param.chunk_size,  # 分块最大字符数；合并阶段尽量凑到不超过该长度
                overlap=param.overlap,  # 超长硬切时相邻块的重叠字符数
            )
        raise ServiceException(message=f'不支持的切分策略: {param.split_type}')
