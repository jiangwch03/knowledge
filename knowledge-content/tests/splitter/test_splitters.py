import re

import pytest

from knowledge_common.exceptions.exception import ServiceException
from knowledge_content.enums.split_type_enum import SplitType
from knowledge_content.splitter.factory import DocumentSplitterFactory
from knowledge_content.splitter.fixed_length_splitter import FixedLengthTextSplitter
from knowledge_content.splitter.markdown_header_parent import MarkdownHeaderParentTextSplitter
from knowledge_content.splitter.regex_splitter import RegexTextSplitter
from knowledge_content.splitter.vo import DocumentSplitParamVo


def test_factory_selection():
    title = DocumentSplitterFactory.get(
        DocumentSplitParamVo(split_type=SplitType.TITLE, chunk_size=500, title_level=2),
    )
    assert isinstance(title, MarkdownHeaderParentTextSplitter)
    assert title.return_each_line is False

    smart = DocumentSplitterFactory.get(
        DocumentSplitParamVo(split_type=SplitType.SMART, chunk_size=1000),
    )
    assert isinstance(smart, MarkdownHeaderParentTextSplitter)
    assert smart.return_each_line is True
    assert smart.overlap == 100

    length = DocumentSplitterFactory.get(
        DocumentSplitParamVo(split_type=SplitType.LENGTH, chunk_size=200, overlap=20),
    )
    assert isinstance(length, FixedLengthTextSplitter)

    separator = DocumentSplitterFactory.get(
        DocumentSplitParamVo(
            split_type=SplitType.SEPARATOR,
            chunk_size=100,
            separator=r'\n\n',
        ),
    )
    assert isinstance(separator, RegexTextSplitter)
    assert separator.pattern == re.escape('\n\n')

    regex = DocumentSplitterFactory.get(
        DocumentSplitParamVo(
            split_type=SplitType.REGEX,
            chunk_size=100,
            regex=r'[。！？]',
        ),
    )
    assert isinstance(regex, RegexTextSplitter)


def test_title_parent_child_oversize():
    text = '# Title\n' + ('word ' * 200)
    splitter = DocumentSplitterFactory.get(
        DocumentSplitParamVo(
            split_type=SplitType.TITLE,
            chunk_size=100,
            overlap=10,
            title_level=1,
        ),
    )
    segments = splitter.split(text)

    assert len(segments) > 1
    parent = segments[0]
    assert parent.skip_embedding is True
    assert parent.chunk_id
    assert parent.metadata.title == 'Title'

    children = [segment for segment in segments[1:] if segment.parent_chunk_id]
    assert children
    assert all(child.parent_chunk_id == parent.chunk_id for child in children)
    assert all(child.skip_embedding is False for child in children)


def test_code_block_hash_not_header():
    text = """# Real Header
```python
# Not a header
print('hi')
```
After code
"""
    splitter = DocumentSplitterFactory.get(
        DocumentSplitParamVo(
            split_type=SplitType.TITLE,
            chunk_size=500,
            title_level=1,
        ),
    )
    segments = splitter.split(text)

    assert len(segments) == 1
    assert segments[0].metadata.title == 'Real Header'
    assert '# Not a header' in segments[0].text
    assert 'After code' in segments[0].text


def test_smart_overlap_rewrite():
    param = DocumentSplitParamVo(split_type=SplitType.SMART, chunk_size=1000, overlap=999)
    assert param.overlap == 100

    splitter = DocumentSplitterFactory.get(param)
    assert splitter.overlap == 100


def test_length_basic():
    text = 'alpha beta gamma delta epsilon zeta eta theta'
    splitter = DocumentSplitterFactory.get(
        DocumentSplitParamVo(
            split_type=SplitType.LENGTH,
            chunk_size=20,
            overlap=5,
        ),
    )
    segments = splitter.split(text)

    assert segments
    assert all(segment.chunk_id for segment in segments)
    assert all(segment.metadata.title is None for segment in segments)
    # 允许轻微超长（soft_limit），不必严格 <= chunk_size
    assert all(len(segment.text) <= splitter._soft_limit for segment in segments)
    joined = ''.join(segment.text for segment in segments)
    assert 'alpha' in joined and 'theta' in joined


def test_length_soft_overflow_keeps_chunk():
    """未超过 25% 容差时不二次硬切。"""
    splitter = FixedLengthTextSplitter(chunk_size=20, overlap=5)
    slightly_over = 'a' * int(splitter.chunk_size * 1.2)
    assert len(slightly_over) <= splitter._soft_limit

    splitter._splitter = type('Stub', (), {'split_text': staticmethod(lambda _: [slightly_over])})()
    segments = splitter.split(slightly_over)

    assert len(segments) == 1
    assert segments[0].text == slightly_over


def test_length_hard_cut_when_far_over():
    """超过 chunk_size 的 25% 时才按字符硬切。"""
    splitter = FixedLengthTextSplitter(chunk_size=20, overlap=5)
    far_over = 'b' * (splitter._soft_limit + 1)
    assert len(far_over) > splitter._soft_limit

    splitter._splitter = type('Stub', (), {'split_text': staticmethod(lambda _: [far_over])})()
    segments = splitter.split(far_over)

    assert len(segments) > 1
    assert all(len(segment.text) <= splitter.chunk_size for segment in segments)


def test_separator_oversize_fallback():
    oversized_part = 'x' * 250
    text = f'aaa\n\n{oversized_part}\n\nbbb'
    splitter = DocumentSplitterFactory.get(
        DocumentSplitParamVo(
            split_type=SplitType.SEPARATOR,
            chunk_size=100,
            overlap=10,
            separator=r'\n\n',
        ),
    )
    segments = splitter.split(text)

    assert segments
    assert all(len(segment.text) <= 100 for segment in segments)
    assert all(segment.chunk_id for segment in segments)


def test_separator_literal_not_regex():
    """字典分隔符按字面量切分，特殊字符不按正则解释。"""
    text = 'left|mid|right'
    splitter = DocumentSplitterFactory.get(
        DocumentSplitParamVo(
            split_type=SplitType.SEPARATOR,
            chunk_size=50,
            overlap=0,
            separator='|',
        ),
    )
    segments = splitter.split(text)
    texts = [segment.text for segment in segments]
    assert 'left' in ''.join(texts)
    assert 'right' in ''.join(texts)
    assert all('|' not in segment.text for segment in segments)


def test_regex_basic():
    text = '第一句。第二句！第三句？'
    splitter = DocumentSplitterFactory.get(
        DocumentSplitParamVo(
            split_type=SplitType.REGEX,
            chunk_size=20,
            overlap=0,
            regex=r'[。！？]',
        ),
    )
    segments = splitter.split(text)

    assert segments
    assert all(segment.chunk_id for segment in segments)
    combined = ''.join(segment.text for segment in segments)
    assert '第一句' in combined
    assert '第三句' in combined


def test_param_validation_errors():
    with pytest.raises(ServiceException, match='重叠长度必须小于块大小'):
        DocumentSplitParamVo(split_type=SplitType.LENGTH, chunk_size=100, overlap=100)

    with pytest.raises(ServiceException, match='标题层级须为 1–6'):
        DocumentSplitParamVo(split_type=SplitType.TITLE, chunk_size=100, title_level=0)

    with pytest.raises(ServiceException, match='分隔符不能为空'):
        DocumentSplitParamVo(split_type=SplitType.SEPARATOR, chunk_size=100)

    with pytest.raises(ServiceException, match='正则表达式不能为空'):
        DocumentSplitParamVo(split_type=SplitType.REGEX, chunk_size=100)

    with pytest.raises(ServiceException, match='正则表达式无效'):
        DocumentSplitParamVo(
            split_type=SplitType.REGEX,
            chunk_size=100,
            regex='[',
        )
