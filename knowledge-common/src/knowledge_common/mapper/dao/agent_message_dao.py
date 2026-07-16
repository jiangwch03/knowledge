from datetime import datetime

from sqlalchemy import select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.do.agent_message_do import AgentMessage
from knowledge_common.utils.page_util import PageUtil


class AgentMessageDao:
    """Agent 消息数据库操作层"""

    @staticmethod
    async def get_message_by_id(message_id: int) -> AgentMessage | None:
        db = get_current_session()
        return (
            (await db.execute(select(AgentMessage).where(
                AgentMessage.message_id == message_id,  # type: ignore
                AgentMessage.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )))
            .scalars()
            .first()
        )

    @staticmethod
    async def get_messages_by_session(
        session_id: int,
        is_page: bool = False,
        page_num: int = 1,
        page_size: int = 50,
    ) -> PageModel | list[AgentMessage]:
        query = select(AgentMessage).where(
            AgentMessage.session_id == session_id,  # type: ignore
            AgentMessage.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
        ).order_by(AgentMessage.create_time.asc())  # type: ignore
        return await PageUtil.paginate(query, page_num, page_size, is_page)

    @staticmethod
    async def add_message(message: AgentMessage) -> AgentMessage:
        db = get_current_session()
        db.add(message)
        await db.flush()
        return message

    @staticmethod
    async def get_by_tool_call_id(session_id: int, tool_call_id: str) -> AgentMessage | None:
        db = get_current_session()
        return (
            (await db.execute(select(AgentMessage).where(
                AgentMessage.session_id == session_id,  # type: ignore
                AgentMessage.tool_call_id == tool_call_id,  # type: ignore
                AgentMessage.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )))
            .scalars()
            .first()
        )

    @staticmethod
    async def update_content_by_id(message_id: int, content: str, update_by: str = '') -> None:
        db = get_current_session()
        await db.execute(
            update(AgentMessage)
            .where(AgentMessage.message_id == message_id)  # type: ignore
            .values(content=content, update_by=update_by, update_time=datetime.now())
        )

    @staticmethod
    async def soft_delete_by_session(session_id: int, update_by: str = '') -> None:
        db = get_current_session()
        await db.execute(
            update(AgentMessage)
            .where(
                AgentMessage.session_id == session_id,  # type: ignore
                AgentMessage.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )
