"""本地圈资料。不调用模型。"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

from knowledge_admin.vo.eval_question_plan_vo import (
    EvalMaterialDocVo,
    EvalPageVo,
    GenerationMaterialPlanVo,
    QuestionQuotaVo,
)

if TYPE_CHECKING:
    from knowledge_common.facade.api.knowledge_content.document_section_vo import DocumentSectionVo

_FULL_FEED_LIMIT = 20
_SIMPLE_SAMPLE_SIZE = 5
_PAGE_CAP = 20
_MD_LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')
_HTML_LINK = re.compile(r"""<a\s+[^>]*href=["']([^"']+)["']""", re.IGNORECASE)


def split_question_quota(question_count: int) -> QuestionQuotaVo:
    """4:2:2:1:1，余数补给简单题。"""
    total = max(question_count, 0)
    base = total // 10
    remainder = total % 10
    return QuestionQuotaVo(
        simple=base * 4 + remainder,
        multi_hop=base * 2,
        comprehensive=base * 2,
        vague=base,
        adversarial=base,
    )


def systematic_sample(count: int, take: int) -> list[int]:
    """按顺序隔一段取，取满就停。多于 1 个时头尾都在里面。"""
    if count <= 0 or take <= 0:
        return []
    if count <= take:
        return list(range(count))
    if take == 1:
        return [0]
    step = count / take
    indexes = [min(int(position * step), count - 1) for position in range(take)]
    indexes[0] = 0
    indexes[-1] = count - 1
    seen: set[int] = set()
    ordered: list[int] = []
    for index in indexes:
        if index in seen:
            continue
        seen.add(index)
        ordered.append(index)
    return ordered


def navigation_urls(pages: list[EvalPageVo], start_indexes: list[int]) -> set[str]:
    """起点页里超过一半都指向的地址，当成导航丢掉。"""
    if not start_indexes:
        return set()
    corpus = _corpus(pages)
    counts: dict[str, int] = {}
    for index in start_indexes:
        if index < 0 or index >= len(pages):
            continue
        pointed: set[str] = set()
        for href in _hrefs(pages[index].text):
            target = _resolve(pages[index].source_url, href)
            if target in corpus and corpus[target] != index:
                pointed.add(target)
        for target in pointed:
            counts[target] = counts.get(target, 0) + 1
    half = len(start_indexes) / 2
    return {url for url, count in counts.items() if count > half}


def multi_hop_page_indexes(pages: list[EvalPageVo], pair_count: int) -> list[int]:
    """每个起点只配一条站内链接。没有就顺延，下一对起点不跟着挪。去重后不超过 20 页。"""
    pages = _reindex_pages(pages)
    total = len(pages)
    if pair_count <= 0 or total == 0:
        return []
    starts = systematic_sample(total, pair_count)
    corpus = _corpus(pages)
    blocked = navigation_urls(pages, starts)
    chosen: set[int] = set()
    for position, start in enumerate(starts):
        boundary = starts[position + 1] if position + 1 < len(starts) else total
        pair = _walk_pair(pages, start, boundary, blocked, corpus)
        if pair is None:
            continue
        if not _admit(chosen, pair):
            break
    return sorted(chosen)


def multi_hop_section_indexes(sections: list[DocumentSectionVo], pair_count: int) -> list[int]:
    """同一上级标题下、挨着的两节配成一对。去重后不超过 20 节。"""
    candidates = _sibling_pairs(sections)
    if pair_count <= 0 or not candidates:
        return []
    chosen: set[int] = set()
    for slot in systematic_sample(len(candidates), pair_count):
        if not _admit(chosen, candidates[slot]):
            break
    return sorted(chosen)


def plan_from_pages(pages: list[EvalPageVo], question_count: int) -> GenerationMaterialPlanVo:
    pages = _reindex_pages(pages)
    quota = split_question_quota(question_count)
    docs = [_page_doc(page) for page in pages]
    if len(pages) <= _FULL_FEED_LIMIT:
        return _same_batch(docs, quota)
    simple_indexes = systematic_sample(len(pages), _SIMPLE_SAMPLE_SIZE)
    multi_docs = [docs[index] for index in multi_hop_page_indexes(pages, quota.multi_hop)]
    return GenerationMaterialPlanVo(
        separate_ragas_calls=True,
        simple_docs=[docs[index] for index in simple_indexes],
        multi_hop_docs=multi_docs,
        custom_docs=list(multi_docs),
        quota=quota,
    )


def plan_from_sections(sections: list[DocumentSectionVo], question_count: int) -> GenerationMaterialPlanVo:
    usable = [section for section in sections if section.body.strip()]
    quota = split_question_quota(question_count)
    docs = [_section_doc(section) for section in usable]
    if len(usable) <= _FULL_FEED_LIMIT:
        return _same_batch(docs, quota)
    simple_indexes = systematic_sample(len(usable), _SIMPLE_SAMPLE_SIZE)
    multi_docs = [docs[index] for index in multi_hop_section_indexes(usable, quota.multi_hop)]
    return GenerationMaterialPlanVo(
        separate_ragas_calls=True,
        simple_docs=[docs[index] for index in simple_indexes],
        multi_hop_docs=multi_docs,
        custom_docs=list(multi_docs),
        quota=quota,
    )


def plan_has_material(plan: GenerationMaterialPlanVo) -> bool:
    docs = [*plan.simple_docs, *plan.custom_docs]
    return any(doc.page_content.strip() for doc in docs)


def _same_batch(docs: list[EvalMaterialDocVo], quota: QuestionQuotaVo) -> GenerationMaterialPlanVo:
    return GenerationMaterialPlanVo(
        separate_ragas_calls=False,
        simple_docs=list(docs),
        multi_hop_docs=list(docs),
        custom_docs=list(docs),
        quota=quota,
    )


def _sibling_pairs(sections: list[DocumentSectionVo]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for index in range(len(sections) - 1):
        left = sections[index]
        right = sections[index + 1]
        if left.parent_title and left.parent_title == right.parent_title:
            pairs.append((index, index + 1))
    return pairs


def _walk_pair(
    pages: list[EvalPageVo],
    start: int,
    boundary: int,
    blocked: set[str],
    corpus: dict[str, int],
) -> tuple[int, int] | None:
    cursor = start
    while cursor < boundary:
        target = _first_target_index(pages[cursor], blocked, corpus)
        if target is not None:
            return cursor, target
        cursor += 1
    return None


def _first_target_index(page: EvalPageVo, blocked: set[str], corpus: dict[str, int]) -> int | None:
    for href in _hrefs(page.text):
        target = _resolve(page.source_url, href)
        if not target or target in blocked or target not in corpus:
            continue
        target_index = corpus[target]
        if target_index == page.index:
            continue
        return target_index
    return None


def _admit(chosen: set[int], pair: tuple[int, int]) -> bool:
    extra = [index for index in pair if index not in chosen]
    if len(chosen) + len(extra) > _PAGE_CAP:
        return False
    chosen.update(pair)
    return True


def _reindex_pages(pages: list[EvalPageVo]) -> list[EvalPageVo]:
    return [page.model_copy(update={'index': index}) for index, page in enumerate(pages)]


def _corpus(pages: list[EvalPageVo]) -> dict[str, int]:
    found: dict[str, int] = {}
    for page in pages:
        key = _normalize_url(page.source_url)
        if key and key not in found:
            found[key] = page.index
    return found


def _page_doc(page: EvalPageVo) -> EvalMaterialDocVo:
    return EvalMaterialDocVo(
        page_content=page.text,
        file_id=page.file_id,
        doc_name=page.doc_name,
        source_url=page.source_url,
    )


def _section_doc(section: DocumentSectionVo) -> EvalMaterialDocVo:
    return EvalMaterialDocVo(
        page_content=section.body,
        title=section.title,
    )


def _hrefs(text: str) -> list[str]:
    found = [(match.start(), match.group(1)) for match in _MD_LINK.finditer(text)]
    found.extend((match.start(), match.group(1)) for match in _HTML_LINK.finditer(text))
    found.sort(key=lambda item: item[0])
    return [href for _, href in found]


def _resolve(page_url: str, href: str) -> str:
    raw = href.strip()
    lowered = raw.lower()
    if not raw or raw.startswith('#') or lowered.startswith(('mailto:', 'javascript:')):
        return ''
    return _normalize_url(urljoin(page_url, raw))


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ''
    path = parsed.path.rstrip('/') or '/'
    query = f'?{parsed.query}' if parsed.query else ''
    return f'{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}{query}'
