"""按标题块用 jieba.analyse.extract_tags 抽主题关键词。"""

from __future__ import annotations

import re
from dataclasses import dataclass

import jieba.analyse
import jieba.posseg

from knowledge_content.service.topic_keyword_common_en import COMMON_ENGLISH
from knowledge_content.service.topic_keyword_en_class import EN_WORD_CLASS
from knowledge_content.vo.retrieve_topic_vo import TopicKeywordWeightVo, TopicSourceSegmentVo

_ALLOW_POS = ('n', 'nz', 'eng')
# 至少在两段正文里出现过。只写过一次的代号、哈希不进词表。
_MIN_SEGMENTS = 2
# jieba 新闻词频里低于这条的，是日常汉语。向量 9.3、分析器 11.6，不会被划进来。
_ZH_IDF_MAX = 7.0
# 文档的词频是 9.99，划不进上面那条，但它和「数据」一样会误开检索。
_ZH_EXTRA = frozenset({'文档'})
# 日常词表里又是这套文档的专名。问句里可能只靠这一个词。
_KEEP_EVERYDAY = frozenset({'standard', 'index', 'collection', 'cluster'})
_HEX_BLOB = re.compile(r'^[0-9a-fA-F]{8,}$')
# 语种和词类分开。虚词取中学语法：副词、介词、连词、助词、叹词、语气词。
LANG_ZH = 'zh'
LANG_EN = 'en'
WORD_CLASS_NOUN = 'noun'
WORD_CLASS_VERB = 'verb'
WORD_CLASS_ADJ = 'adj'
WORD_CLASS_FUNCTION = 'function'
WORD_CLASS_OTHER = 'other'
# 来源。手工补进表里的，以及后来在页面上新增的，标成手工录入。
SOURCE_ZH_IDF = 'zh_idf'
SOURCE_EN_COMMON = 'en_common'
SOURCE_MANUAL = 'manual'
_FUNCTION_FLAGS = frozenset({'d', 'p', 'c', 'u', 'e', 'y', 'uj', 'ul', 'uz', 'uv', 'ud', 'ug'})
_everyday_chinese: frozenset[str] | None = None


@dataclass
class _KeywordTally:
    keyword: str
    weight: float
    segments: int


def _everyday_chinese_words() -> frozenset[str]:
    global _everyday_chinese
    if _everyday_chinese is None:
        words = {
            word
            for word, idf in jieba.analyse.default_tfidf.idf_freq.items()
            if idf < _ZH_IDF_MAX
        }
        words.update(_ZH_EXTRA)
        _everyday_chinese = frozenset(words)
    return _everyday_chinese


def _fold(word: str) -> str:
    if word.isascii():
        return word.casefold()
    return word


def _is_identifier(word: str) -> bool:
    """queryNode、BM25 这种写法。仅首字母大写的 Collection、全大写的 DROP 不算。"""
    if _HEX_BLOB.fullmatch(word):
        return False
    has_letter = any(ch.isalpha() for ch in word)
    has_digit = any(ch.isdigit() for ch in word)
    if has_letter and has_digit:
        return True
    has_lower = any(ch.islower() for ch in word)
    return has_lower and any(ch.isupper() for ch in word[1:])


@dataclass(frozen=True)
class EverydayWordKind:
    """语种是中文还是英文。词类是名词、动词、形容词、虚词、其他。"""

    lang: str
    word_class: str


def classify_everyday_word(word: str) -> EverydayWordKind:
    """先看语种，再看词类。英文词类按常用英语词表，中文按 jieba 词性。"""
    text = word.strip()
    if not text or text.isascii():
        folded = text.casefold()
        return EverydayWordKind(LANG_EN, EN_WORD_CLASS.get(folded, WORD_CLASS_OTHER))
    pairs = list(jieba.posseg.cut(text))
    flag = pairs[0].flag if pairs else 'x'
    if flag.startswith('n'):
        word_class = WORD_CLASS_NOUN
    elif flag.startswith('v'):
        word_class = WORD_CLASS_VERB
    elif flag.startswith('a'):
        word_class = WORD_CLASS_ADJ
    elif flag in _FUNCTION_FLAGS or flag[:1] in _FUNCTION_FLAGS:
        word_class = WORD_CLASS_FUNCTION
    else:
        word_class = WORD_CLASS_OTHER
    return EverydayWordKind(LANG_ZH, word_class)


def everyday_word_source(word: str) -> str:
    """中文词频表、常用英语、手工录入。文档不在词频门槛里，算手工录入。"""
    text = word.strip()
    if text in _ZH_EXTRA:
        return SOURCE_MANUAL
    folded = text.casefold() if text.isascii() else text
    if text in COMMON_ENGLISH or folded in COMMON_ENGLISH:
        return SOURCE_EN_COMMON
    if text in _everyday_chinese_words():
        return SOURCE_ZH_IDF
    return SOURCE_MANUAL


def builtin_everyday_seed() -> tuple[frozenset[str], frozenset[str]]:
    """全部日常词，以及内置时已经剔除的词。"""
    words = set(_everyday_chinese_words())
    words.update(COMMON_ENGLISH)
    return frozenset(words), _KEEP_EVERYDAY


def _builtin_everyday() -> frozenset[str]:
    words, kept = builtin_everyday_seed()
    return frozenset(word for word in words if word not in kept and word.casefold() not in kept)


def _active_everyday(everyday: frozenset[str] | None) -> frozenset[str]:
    if everyday is not None:
        return everyday
    return _builtin_everyday()


def _in_everyday(word: str, everyday: frozenset[str]) -> bool:
    if word in everyday:
        return True
    return bool(word.isascii() and word.isalpha() and word.casefold() in everyday)


def _keep_keyword(
    word: str,
    segments: int,
    *,
    require_repeat: bool,
    everyday: frozenset[str] | None = None,
) -> bool:
    text = word.strip()
    if len(text) < 2 or _HEX_BLOB.fullmatch(text):
        return False
    if require_repeat and segments < _MIN_SEGMENTS:
        return False
    if _is_identifier(text):
        return True
    return not _in_everyday(text, _active_everyday(everyday))


def is_topic_source_segment(segment: TopicSourceSegmentVo) -> bool:
    """有父块时只取父块；没有父块时取这块本身。"""
    if segment.skip_embedding == 1:
        return True
    return not (segment.parent_chunk_id or '').strip()


def select_source_texts(segments: list[TopicSourceSegmentVo]) -> list[str]:
    texts: list[str] = []
    for segment in segments:
        if not is_topic_source_segment(segment):
            continue
        body = (segment.text or '').strip()
        if body:
            texts.append(body)
    return texts


def merge_keyword_weights(
    items: list[TopicKeywordWeightVo],
    everyday: frozenset[str] | None = None,
) -> list[TopicKeywordWeightVo]:
    """同一词保留较高权重。日常词丢掉，专名写法留下。"""
    best: dict[str, tuple[str, float]] = {}
    for item in items:
        word = item.keyword.strip()
        if not _keep_keyword(word, 0, require_repeat=False, everyday=everyday):
            continue
        key = _fold(word)
        previous = best.get(key)
        if previous is None or item.weight > previous[1]:
            best[key] = (word, item.weight)
    ranked = sorted(best.values(), key=lambda pair: (-pair[1], pair[0]))
    return [TopicKeywordWeightVo(keyword=word, weight=weight) for word, weight in ranked]


def resolve_topic_keywords(
    fresh: list[TopicKeywordWeightVo],
    existing: list[TopicKeywordWeightVo],
    *,
    keep: bool,
    everyday: frozenset[str] | None = None,
) -> list[TopicKeywordWeightVo]:
    if keep:
        return merge_keyword_weights([*existing, *fresh], everyday)
    return merge_keyword_weights(fresh, everyday)


def extract_topic_keywords(
    texts: list[str],
    everyday: frozenset[str] | None = None,
) -> list[TopicKeywordWeightVo]:
    """对每段正文调用 extract_tags。只出现一次的丢掉，日常词丢掉。"""
    tallies: dict[str, _KeywordTally] = {}
    for text in texts:
        body = text.strip()
        if not body:
            continue
        pairs = jieba.analyse.extract_tags(body, topK=None, withWeight=True, allowPOS=_ALLOW_POS)
        seen: set[str] = set()
        for word, weight in pairs:
            text_word = str(word).strip()
            if not text_word:
                continue
            key = _fold(text_word)
            if key in seen:
                continue
            seen.add(key)
            current = tallies.get(key)
            if current is None:
                tallies[key] = _KeywordTally(keyword=text_word, weight=float(weight), segments=1)
                continue
            current.segments += 1
            if float(weight) > current.weight:
                current.keyword = text_word
                current.weight = float(weight)
    kept = [
        tally
        for tally in tallies.values()
        if _keep_keyword(tally.keyword, tally.segments, require_repeat=True, everyday=everyday)
    ]
    kept.sort(key=lambda tally: (-tally.weight, tally.keyword))
    return [TopicKeywordWeightVo(keyword=tally.keyword, weight=tally.weight) for tally in kept]
