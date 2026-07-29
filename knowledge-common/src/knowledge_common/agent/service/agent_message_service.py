import json
from typing import Any

from knowledge_common.agent.enums.message_role_enum import MessageRoleLangchain
from knowledge_common.agent.schema.agent_message_resp_vo import AgentMessageRespVo
from knowledge_common.agent.schema.message_vo import AgentMessageVo
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import PageModel
from knowledge_common.mapper.dao.agent_message_dao import AgentMessageDao
from knowledge_common.mapper.do.agent_message_do import AgentMessage


def _dump_tool_content(tool_name: str, tool_args: Any = None, result: Any = None) -> str:
    """工具消息 content 统一编码为 JSON，承载调用 + 结果全流程信息。"""
    payload: dict[str, Any] = {'tool_name': tool_name}
    if tool_args is not None:
        payload['tool_args'] = tool_args
    if result is not None:
        payload['result'] = result
    return json.dumps(payload, ensure_ascii=False)


class AgentMessageService:
    """Agent 消息服务层，负责消息 CRUD、历史查询。"""

    @staticmethod
    def _to_vo(message: AgentMessage) -> AgentMessageRespVo:
        return AgentMessageRespVo.model_validate(message)

    @classmethod
    def _to_vo_page(cls, result: PageModel | list[AgentMessage]) -> PageModel[AgentMessageRespVo] | list[AgentMessageRespVo]:
        if isinstance(result, PageModel):
            result.rows = [cls._to_vo(item) for item in result.rows]
            return result
        return [cls._to_vo(item) for item in result]

    @classmethod
    @transactional(read_only=True)
    async def get_messages(
        cls,
        session_id: int,
        page_num: int = 1,
        page_size: int = 50,
        is_page: bool = True,
    ) -> PageModel[AgentMessageRespVo] | list[AgentMessageRespVo]:
        result = await AgentMessageDao.get_messages_by_session(
            session_id=session_id,
            is_page=is_page,
            page_num=page_num,
            page_size=page_size,
        )
        return cls._to_vo_page(result)

    @classmethod
    @transactional()
    async def add_user_message(cls, vo: AgentMessageVo) -> int:
        message = AgentMessage(
            session_id=vo.session_id,
            role=MessageRoleLangchain.HUMAN.value,
            content=vo.content,
            user_id=vo.user_id,
            dept_id=vo.dept_id,
            create_by=vo.create_by,
            update_by=vo.update_by,
            tool_call_id=vo.tool_call_id,
            tool_name=vo.tool_name,
        )
        await AgentMessageDao.add_message(message)
        return message.message_id

    @classmethod
    @transactional()
    async def add_assistant_message(cls, vo: AgentMessageVo) -> AgentMessage:
        message = AgentMessage(
            session_id=vo.session_id,
            role=MessageRoleLangchain.AI.value,
            content=vo.content,
            user_id=vo.user_id,
            dept_id=vo.dept_id,
            create_by=vo.create_by,
            update_by=vo.create_by,
            tool_call_id=vo.tool_call_id,
            tool_name=vo.tool_name,
            remark=vo.remark,
        )
        return await AgentMessageDao.add_message(message)

    @classmethod
    @transactional()
    async def add_tool_message(cls, vo: AgentMessageVo) -> AgentMessage:
        message = AgentMessage(
            session_id=vo.session_id,
            role=MessageRoleLangchain.TOOL.value,
            content=vo.content,
            tool_call_id=vo.tool_call_id,
            tool_name=vo.tool_name,
            user_id=vo.user_id,
            dept_id=vo.dept_id,
            create_by=vo.create_by,
            update_by=vo.create_by,
        )
        return await AgentMessageDao.add_message(message)

    @classmethod
    @transactional()
    async def save_tool_call(
        cls,
        session_id: int,
        tool_call_id: str,
        tool_name: str,
        tool_args: Any,
        user_id: int,
        dept_id: int | None = None,
        create_by: str | None = None,
        remark: str | None = None,
    ) -> int:
        message = AgentMessage(
            session_id=session_id,
            role=MessageRoleLangchain.TOOL.value,
            content=_dump_tool_content(tool_name, tool_args=tool_args),
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            user_id=user_id,
            dept_id=dept_id,
            create_by=create_by,
            update_by=create_by,
            remark=remark,
        )
        await AgentMessageDao.add_message(message)
        return message.message_id

    @classmethod
    @transactional()
    async def complete_tool_call(
        cls,
        session_id: int,
        tool_call_id: str,
        tool_name: str,
        result: Any,
        user_id: int,
        dept_id: int | None = None,
        create_by: str | None = None,
        remark: str | None = None,
    ) -> None:
        existing = await AgentMessageDao.get_by_tool_call_id(session_id, tool_call_id)
        if existing is None:
            message = AgentMessage(
                session_id=session_id,
                role=MessageRoleLangchain.TOOL.value,
                content=_dump_tool_content(tool_name, result=result),
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                user_id=user_id,
                dept_id=dept_id,
                create_by=create_by,
                update_by=create_by,
                remark=remark,
            )
            await AgentMessageDao.add_message(message)
            return

        try:
            payload = json.loads(existing.content) if existing.content else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}
        payload['tool_name'] = tool_name or payload.get('tool_name')
        payload['result'] = result
        await AgentMessageDao.update_content_by_id(
            existing.message_id, json.dumps(payload, ensure_ascii=False), update_by=create_by or ''
        )

    @classmethod
    @transactional()
    async def add_business_stream_message(cls, vo: AgentMessageVo, *, role: str) -> AgentMessage:
        """业务旁路落库；role 统一为 business，content 为 data 的 JSON。"""
        message = AgentMessage(
            session_id=vo.session_id,
            role=role,
            content=vo.content,
            user_id=vo.user_id,
            dept_id=vo.dept_id,
            create_by=vo.create_by,
            update_by=vo.create_by,
            remark=vo.remark,
        )
        return await AgentMessageDao.add_message(message)

    @classmethod
    @transactional()
    async def add_system_message(cls, vo: AgentMessageVo) -> AgentMessage:
        message = AgentMessage(
            session_id=vo.session_id,
            role=MessageRoleLangchain.SYSTEM.value,
            content=vo.content,
            user_id=vo.user_id,
            dept_id=vo.dept_id,
            create_by=vo.create_by,
            update_by=vo.create_by,
            tool_call_id=vo.tool_call_id,
            tool_name=vo.tool_name,
        )
        return await AgentMessageDao.add_message(message)
