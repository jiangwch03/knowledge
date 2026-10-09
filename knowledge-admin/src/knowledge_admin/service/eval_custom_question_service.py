"""模糊题、对抗题、综合题。不走 RAGAS。"""
from __future__ import annotations

from typing import Any

from knowledge_common.config.prompt_config import prompt_config
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger

from knowledge_admin.vo.eval_question_plan_vo import (
    CustomQuestionBatchVo,
    CustomQuestionDraftVo,
    EvalMaterialDocVo,
    QuestionQuotaVo,
)
from knowledge_admin.vo.eval_vo import GeneratedDatasetItemVo

_UNKNOWN = '不知道'
_EXCERPT_FALLBACK_CHARS = 400
_PROMPT_KEY = 'eval_dataset_custom_questions'


class EvalCustomQuestionService:
    """用测评集对话模型，按圈好的材料写后三类题。"""

    @classmethod
    async def generate(
        cls,
        chat: Any,
        docs: list[EvalMaterialDocVo],
        quota: QuestionQuotaVo,
    ) -> list[GeneratedDatasetItemVo]:
        if not docs or not _needs_custom(quota):
            return []
        system = prompt_config.get_system_prompt(_PROMPT_KEY)
        if not system:
            raise ServiceException(message='未配置测评集出题提示词')
        # 步骤1：一次结构化调用，按道数写出三类题
        raw = await chat.with_structured_output(CustomQuestionBatchVo).ainvoke(
            [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': _user_message(docs, quota)},
            ]
        )
        batch = raw if isinstance(raw, CustomQuestionBatchVo) else CustomQuestionBatchVo.model_validate(raw)
        # 步骤2：对抗题标准答案固定，并按配额截断
        items = cls.assemble(batch, quota, docs)
        logger.info(
            '[EvalCustomQuestion] 完成 comprehensive={} vague={} adversarial={}',
            quota.comprehensive,
            quota.vague,
            quota.adversarial,
        )
        return items

    @classmethod
    def assemble(
        cls,
        batch: CustomQuestionBatchVo,
        quota: QuestionQuotaVo,
        docs: list[EvalMaterialDocVo],
    ) -> list[GeneratedDatasetItemVo]:
        fallback = _fallback_excerpt(docs)
        items: list[GeneratedDatasetItemVo] = []
        items.extend(_take(batch.comprehensive, quota.comprehensive, 'comprehensive', fallback, False))
        items.extend(_take(batch.vague, quota.vague, 'vague', fallback, False))
        items.extend(_take(batch.adversarial, quota.adversarial, 'adversarial', fallback, True))
        return items


def _needs_custom(quota: QuestionQuotaVo) -> bool:
    return quota.comprehensive + quota.vague + quota.adversarial > 0


def _user_message(docs: list[EvalMaterialDocVo], quota: QuestionQuotaVo) -> str:
    lines = [
        f'综合题 {quota.comprehensive} 道。',
        f'模糊题 {quota.vague} 道。',
        f'对抗题 {quota.adversarial} 道。',
        '某类道数为 0 时，该类返回空列表。',
        '材料如下：',
    ]
    for index, doc in enumerate(docs, start=1):
        label = doc.title or doc.doc_name or doc.source_url or f'材料{index}'
        lines.append(f'\n## 材料 {index} {label}\n{doc.page_content}')
    return '\n'.join(lines)


def _take(
    drafts: list[CustomQuestionDraftVo],
    limit: int,
    difficulty: str,
    fallback: str,
    force_unknown: bool,
) -> list[GeneratedDatasetItemVo]:
    if limit <= 0:
        return []
    items: list[GeneratedDatasetItemVo] = []
    for draft in drafts:
        if len(items) >= limit:
            break
        question = draft.question.strip()
        if not question:
            continue
        excerpts = [excerpt.strip() for excerpt in draft.excerpts if excerpt.strip()]
        if not excerpts and fallback:
            excerpts = [fallback]
        ground_truth = _UNKNOWN if force_unknown else draft.ground_truth.strip()
        items.append(
            GeneratedDatasetItemVo(
                question=question,
                ground_truth=ground_truth,
                difficulty=difficulty,
                reference_excerpts=excerpts,
            )
        )
    return items


def _fallback_excerpt(docs: list[EvalMaterialDocVo]) -> str:
    for doc in docs:
        text = doc.page_content.strip()
        if text:
            return text[:_EXCERPT_FALLBACK_CHARS]
    return ''
