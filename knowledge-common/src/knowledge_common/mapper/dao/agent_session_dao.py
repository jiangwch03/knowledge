from datetime import datetime

from sqlalchemy import ColumnElement, select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.do.agent_session_do import AgentSession
from knowledge_common.utils.page_util import PageUtil
from knowledge_common.mapper.dao.base_dao import BaseDao


class AgentSessionDao(BaseDao):
    """Agent 会话数据库操作层"""

    @staticmethod
    async def get_session_by_id(session_id: int) -> AgentSession | None:
        db = get_current_session()
        return (
            (await db.execute(select(AgentSession).where(
                AgentSession.session_id == session_id,  # type: ignore
                AgentSession.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )))
            .scalars()
            .first()
        )

    @staticmethod
    async def get_session_list(
        agent_type: str,
        user_id: int,
        title: str | None = None,
        is_page: bool = False,
        page_num: int = 1,
        page_size: int = 20,
        data_scope_sql: ColumnElement | None = None,
    ) -> PageModel | list[AgentSession]:
        query = select(AgentSession).where(
            AgentSession.agent_type == agent_type,  # type: ignore
            AgentSession.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
        )
        if data_scope_sql is not None:
            query = query.where(data_scope_sql)
        else:
            query = query.where(AgentSession.user_id == user_id)  # type: ignore
        if title:
            query = query.where(AgentSession.session_title.like(f'%{title}%'))  # type: ignore
        query = query.order_by(AgentSession.session_id.desc())  # type: ignore
        return await PageUtil.paginate(query, page_num, page_size, is_page)

    @staticmethod
    async def add_session(session: AgentSession) -> AgentSession:
        db = get_current_session()
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session

    @staticmethod
    async def update_session_title(session_id: int, session_title: str, update_by: str = '') -> None:
        db = get_current_session()
        values: dict = {'session_title': session_title, 'update_time': datetime.now()}
        if update_by:
            values['update_by'] = update_by
        await db.execute(
            update(AgentSession)
            .where(AgentSession.session_id == session_id)  # type: ignore
            .values(**values)
        )

    @staticmethod
    async def update_session_status(session_id: int, status: str, update_by: str = '') -> None:
        db = get_current_session()
        values: dict = {'status': status, 'update_time': datetime.now()}
        if update_by:
            values['update_by'] = update_by
        await db.execute(
            update(AgentSession)
            .where(AgentSession.session_id == session_id)  # type: ignore
            .values(**values)
        )

    @staticmethod
    async def soft_delete(session_id: int, update_by: str = '') -> None:
        db = get_current_session()
        await db.execute(
            update(AgentSession)
            .where(AgentSession.session_id == session_id)  # type: ignore
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )
