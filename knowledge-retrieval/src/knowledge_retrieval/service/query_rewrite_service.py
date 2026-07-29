"""检索查询改写：口语规范化、指代消解、多轮拼成独立检索句。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from knowledge_common.agent.enums.message_role_enum import MessageRoleLangchain
from knowledge_common.agent.service.agent_message_service import AgentMessageService
from knowledge_common.config.prompt_config import prompt_config
from knowledge_common.utils.log_util import logger
from knowledge_retrieval.agents.utils.llm_util import get_base_chat_model
from knowledge_retrieval.vo.query_rewrite_vo import QueryRewriteRequestVo

_HISTORY_ROLES = {MessageRoleLangchain.HUMAN.value, MessageRoleLangchain.AI.value}
_MAX_HISTORY_TURNS = 8
_MAX_MSG_CHARS = 400


class _RewriteLlmOut(BaseModel):
    query: str = Field(description='适合向量/关键词检索的独立完整问句')


class QueryRewriteService:
    """查询改写：失败或无提示词时原样返回用户问题。"""

    @classmethod
    async def rewrite(cls, request: QueryRewriteRequestVo) -> str:
        original = (request.question or '').strip()
        if not original:
            return original

        system = prompt_config.get_system_prompt('query_rewrite')
        if not system:
            logger.warning('[QueryRewrite] prompts.yaml 缺少 query_rewrite.system，使用原问句')
            return original

        history = request.history
        if history is None and request.session_id is not None:
            history = await cls.load_recent_history(request.session_id)

        try:
            model = await get_base_chat_model(request.model_id)
            raw = await model.with_structured_output(_RewriteLlmOut).ainvoke(
                [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': cls._build_user_prompt(original, history or [])},
                ]
            )
            out = raw if isinstance(raw, _RewriteLlmOut) else _RewriteLlmOut.model_validate(raw)
            rewritten = (out.query or '').strip()
            if not rewritten:
                return original
            if rewritten != original:
                logger.info('[QueryRewrite] {} -> {}', original[:80], rewritten[:80])
            return rewritten
        except Exception as exc:
            logger.opt(exception=True).warning('[QueryRewrite] 改写失败，使用原问句: {}', exc)
            return original

    @classmethod
    async def load_recent_history(cls, session_id: int) -> list:
        """取会话近期 human/ai 消息（升序）；本轮用户消息尚未入库。"""
        rows = await AgentMessageService.get_messages(
            session_id=session_id,
            page_num=1,
            page_size=50,
            is_page=False,
        )
        if not isinstance(rows, list):
            rows = list(getattr(rows, 'rows', None) or [])
        filtered = [
            m
            for m in rows
            if getattr(m, 'role', None) in _HISTORY_ROLES and (getattr(m, 'content', None) or '').strip()
        ]
        return filtered[-_MAX_HISTORY_TURNS * 2 :]

    @classmethod
    def _build_user_prompt(cls, question: str, history: list) -> str:
        if not history:
            return (
                '（无历史对话）\n\n'
                f'当前用户问题：{question}\n\n'
                '请输出适合检索的独立问句。'
            )
        lines: list[str] = ['最近对话：']
        for msg in history:
            role = '用户' if getattr(msg, 'role', None) == MessageRoleLangchain.HUMAN.value else '助手'
            text = (getattr(msg, 'content', None) or '').strip().replace('\n', ' ')
            if len(text) > _MAX_MSG_CHARS:
                text = text[:_MAX_MSG_CHARS] + '…'
            lines.append(f'{role}：{text}')
        lines.append('')
        lines.append(f'当前用户问题：{question}')
        lines.append('')
        lines.append('请结合上下文，输出适合检索的独立问句。')
        return '\n'.join(lines)
