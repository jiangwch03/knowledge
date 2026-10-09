"""主题抽词：父块选取、权重合并、extract_tags 截断。"""

from knowledge_content.service.topic_keyword_extractor import (
    classify_everyday_word,
    everyday_word_source,
    extract_topic_keywords,
    merge_keyword_weights,
    resolve_topic_keywords,
    select_source_texts,
)
from knowledge_content.vo.retrieve_topic_vo import TopicKeywordWeightVo, TopicSourceSegmentVo


def _weight(keyword: str, weight: float) -> TopicKeywordWeightVo:
    return TopicKeywordWeightVo(keyword=keyword, weight=weight)


def test_everyday_word_class():
    data = classify_everyday_word('data')
    assert data.lang == 'en'
    assert data.word_class == 'noun'
    assert classify_everyday_word('the').word_class == 'function'
    assert classify_everyday_word('run').word_class == 'verb'
    name = classify_everyday_word('名字')
    assert name.lang == 'zh'
    assert name.word_class == 'noun'
    assert classify_everyday_word('数据').word_class == 'noun'
    assert classify_everyday_word('运行').word_class == 'verb'
    assert classify_everyday_word('的').word_class == 'function'
    assert classify_everyday_word('和').word_class == 'function'


def test_everyday_word_source():
    assert everyday_word_source('数据') == 'zh_idf'
    assert everyday_word_source('的') == 'zh_idf'
    assert everyday_word_source('data') == 'en_common'
    assert everyday_word_source('the') == 'en_common'
    assert everyday_word_source('文档') == 'manual'
    assert everyday_word_source('向量') == 'manual'


def test_parent_is_used_and_child_is_skipped():
    segments = [
        TopicSourceSegmentVo(text='父块全文', parent_chunk_id=None, skip_embedding=1),
        TopicSourceSegmentVo(text='子块重叠', parent_chunk_id='parent-1', skip_embedding=0),
        TopicSourceSegmentVo(text='独立块', parent_chunk_id='', skip_embedding=0),
        TopicSourceSegmentVo(text='   ', parent_chunk_id=None, skip_embedding=0),
    ]

    assert select_source_texts(segments) == ['父块全文', '独立块']


def test_merge_keeps_higher_weight_without_cap():
    merged = merge_keyword_weights(
        [
            _weight('分析器', 1.2),
            _weight('分析器', 0.4),
            _weight('索引', 0.9),
            _weight('副本', 0.1),
        ],
    )

    assert [item.keyword for item in merged] == ['分析器', '索引', '副本']
    assert merged[0].weight == 1.2


def test_keep_merges_old_keywords_and_clear_drops_them():
    fresh = [_weight('分析器', 1.0), _weight('索引', 0.5)]
    existing = [_weight('副本', 2.0), _weight('分析器', 0.2)]

    kept = resolve_topic_keywords(fresh, existing, keep=True)
    cleared = resolve_topic_keywords(fresh, existing, keep=False)

    assert [item.keyword for item in kept] == ['副本', '分析器', '索引']
    assert kept[1].weight == 1.0
    assert [item.keyword for item in cleared] == ['分析器', '索引']


def test_extract_tags_keeps_every_tag(monkeypatch):
    def fake_extract(text: str, topK: int | None, withWeight: bool, allowPOS: tuple[str, ...]):
        assert withWeight is True
        assert allowPOS == ('n', 'nz', 'eng')
        assert topK is None
        assert '分析器' in text
        return [('分析器', 1.5), ('索引', 0.8), ('副本', 0.1)]

    monkeypatch.setattr(
        'knowledge_content.service.topic_keyword_extractor.jieba.analyse.extract_tags',
        fake_extract,
    )

    keywords = extract_topic_keywords(['父块里的分析器说明', '另一节的分析器', '第三节还是分析器'])

    assert [item.keyword for item in keywords] == ['分析器', '索引', '副本']


def test_everyday_words_drop_and_keep_list_stays(monkeypatch):
    def fake_extract(text: str, topK: int | None, withWeight: bool, allowPOS: tuple[str, ...]):
        return [
            ('user', 1.0),
            ('users', 1.0),
            ('data', 2.0),
            ('common', 1.0),
            ('数据', 3.0),
            ('Search', 2.2),
            ('DROP', 2.1),
            ('a081d357f9e9', 0.4),
            ('Milvus', 5.0),
            ('queryNode', 4.0),
            ('BM25', 3.5),
            ('分析器', 1.5),
            ('standard', 1.2),
            ('collection', 1.1),
        ]

    monkeypatch.setattr(
        'knowledge_content.service.topic_keyword_extractor.jieba.analyse.extract_tags',
        fake_extract,
    )

    words = [item.keyword for item in extract_topic_keywords(['第一段', '第二段'])]

    assert words == ['Milvus', 'queryNode', 'BM25', '分析器', 'standard', 'collection']


def test_passed_everyday_set_is_what_gets_dropped(monkeypatch):
    def fake_extract(text: str, topK: int | None, withWeight: bool, allowPOS: tuple[str, ...]):
        return [('分析器', 2.0), ('数据', 1.0), ('Milvus', 3.0)]

    monkeypatch.setattr(
        'knowledge_content.service.topic_keyword_extractor.jieba.analyse.extract_tags',
        fake_extract,
    )

    words = [item.keyword for item in extract_topic_keywords(['第一段', '第二段'], frozenset({'分析器'}))]

    assert words == ['Milvus', '数据']


def test_word_seen_in_only_one_segment_is_dropped(monkeypatch):
    def fake_extract(text: str, topK: int | None, withWeight: bool, allowPOS: tuple[str, ...]):
        if '只此一段' in text:
            return [('Milvus', 5.0), ('channelTaskTimeout', 1.0), ('分析器', 1.5)]
        return [('分析器', 1.5)]

    monkeypatch.setattr(
        'knowledge_content.service.topic_keyword_extractor.jieba.analyse.extract_tags',
        fake_extract,
    )

    words = [item.keyword for item in extract_topic_keywords(['只此一段', '另一段'])]

    assert words == ['分析器']


def test_extract_tags_finds_analyzer_noun():
    text = '标准分析器按标点切分文本。分析器会处理英文和中文。分析器是全文检索的组件。'
    keywords = extract_topic_keywords([text, text])
    words = [item.keyword for item in keywords]

    assert '分析器' in words
    assert '数据' not in words
