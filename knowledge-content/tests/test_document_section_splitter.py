"""出题切节：标题、代码围栏、无标题按字数。"""

from knowledge_content.service.document_section_splitter import DocumentSectionSplitter


def test_heading_split_keeps_parent_title():
    text = '# 章\n引言\n## 甲\n甲的正文\n## 乙\n乙的正文\n'
    sections = DocumentSectionSplitter.split(text)

    titled = {section.title: section for section in sections}
    assert titled['甲'].parent_title == '章'
    assert titled['乙'].parent_title == '章'
    assert titled['甲'].section_order < titled['乙'].section_order
    assert '甲的正文' in titled['甲'].body


def test_code_fence_hash_is_not_a_heading():
    text = '# Real\n正文\n```python\n# Not a header\n```\n后面\n## Next\n下一节\n'
    sections = DocumentSectionSplitter.split(text)

    titles = [section.title for section in sections]
    assert titles == ['Real', 'Next']
    real = sections[0]
    assert '# Not a header' in real.body
    assert '后面' in real.body
    assert real.parent_title == ''
    assert sections[1].parent_title == 'Real'


def test_no_heading_splits_about_8000_chars():
    text = 'a' * 9000
    sections = DocumentSectionSplitter.split(text)

    assert len(sections) == 2
    assert sections[0].title == ''
    assert sections[0].parent_title == ''
    assert sections[1].title == ''
    assert sections[1].parent_title == ''
    assert len(sections[0].body) == 8000
    assert sections[0].section_order == 0
    assert sections[1].section_order == 1


def test_paragraph_break_near_8000():
    text = ('b' * 7000) + '\n\n' + ('c' * 2000)
    sections = DocumentSectionSplitter.split(text)

    assert sections[0].body == 'b' * 7000
    assert sections[1].body == 'c' * 2000
