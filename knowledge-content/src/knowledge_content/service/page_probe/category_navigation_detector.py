"""
分类/频道导航检测：课程平台、电商、新闻站顶部分类 Tab。

从渲染后内链样本与可见文本提取分类名事实，供 Agent 决定爬取范围。
"""

from __future__ import annotations

import re

from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo
from knowledge_content.service.vo.page_structure_vo import LinkSampleVo, PageStructureVo

# 课程/内容平台常见分类短语（站点无关词表，用于从可见文本抽取）
_CATEGORY_PHRASES: tuple[str, ...] = (
    '职场办公', '办公软件', '数据分析', '职业成长', '兴趣技能', '摄影摄像',
    '运动健身', '语言学习', '实用英语', '考试考证', '心理', '健康', '人文艺术',
    '前沿科技', '人工智能', '大数据', '编程', '设计', '通识', '考研', '会计',
    '雅思', '托福', '四六级', '新闻', '博客', '教程', '课程',
)

_CATEGORY_HINTS = re.compile(
    r'(?:' + '|'.join(re.escape(p) for p in _CATEGORY_PHRASES) + r')',
    re.IGNORECASE,
)

_NAV_BLOCK_RE = re.compile(
    r'<(?:nav|header)[^>]*>(.*?)</(?:nav|header)>',
    re.DOTALL | re.IGNORECASE,
)


def detect_category_navigation(
    html: str,
    visible_text: str,
    page_structure: PageStructureVo,
) -> InteractiveElementVo | None:
    """检测顶部分类/频道导航"""
    options: list[str] = []
    evidence: list[str] = []

    # 来源 1：可见文本中的已知分类短语
    for phrase in _CATEGORY_PHRASES:
        if phrase in visible_text and phrase not in options:
            options.append(phrase)

    # 来源 2：crawl4ai 内链样本（须含分类语义，避免站点导航链接）
    for sample in page_structure.internal_link_samples:
        label = (sample.text or '').strip()
        if _is_category_label(label) and _CATEGORY_HINTS.search(label):
            if label not in options:
                options.append(label)

    # 来源 3：nav/header 区块内带分类语义的链接
    for block in _NAV_BLOCK_RE.findall(html[:50000]):
        for m in re.finditer(r'<a[^>]*>([^<]{2,20})</a>', block, re.IGNORECASE):
            label = m.group(1).strip()
            if _is_category_label(label) and _CATEGORY_HINTS.search(label) and label not in options:
                options.append(label)

    options = [o for o in options if o not in ('首页', '登录', '注册', '更多', '全部')]

    if len(options) < 3:
        return None

    evidence.append(f'检测到 {len(options)} 个分类/频道入口')
    if page_structure.internal_link_count:
        evidence.append(f'内链总数 {page_structure.internal_link_count}')

    return InteractiveElementVo(
        category='category_navigation',
        confidence=0.7 if len(options) >= 5 else 0.6,
        location='header',
        evidence=evidence,
        options=options[:20],
        impact='ask_user_for_crawl_scope',
    )


def _is_category_label(text: str) -> bool:
    if not text or len(text) < 2 or len(text) > 20:
        return False
    if text.startswith('http'):
        return False
    if re.fullmatch(r'\d+', text):
        return False
    if re.search(r'\d', text) and re.search(r'[门篇条个]', text):
        return False
    return bool(_CATEGORY_HINTS.search(text))
