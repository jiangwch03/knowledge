from sqlalchemy import ColumnElement

from knowledge_common.agent.enums.session_status_enum import SessionStatus
from knowledge_common.agent.memory.short_memory.checkpointer import Checkpointer
from knowledge_common.agent.schema.agent_session_vo import AgentSessionVo
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import PageModel
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.agent_message_dao import AgentMessageDao
from knowledge_common.mapper.dao.agent_session_dao import AgentSessionDao
from knowledge_common.mapper.do.agent_session_do import AgentSession
from knowledge_common.utils.log_util import logger


class AgentSessionService:
    """Agent 会话服务层，负责会话 CRUD、状态管理。"""

    @staticmethod
    def _to_vo(session: AgentSession) -> AgentSessionVo:
        return AgentSessionVo.model_validate(session)

    @classmethod
    def _to_vo_page(cls, result: PageModel | list[AgentSession]) -> PageModel[AgentSessionVo] | list[AgentSessionVo]:
        if isinstance(result, PageModel):
            result.rows = [cls._to_vo(item) for item in result.rows]
            return result
        return [cls._to_vo(item) for item in result]

    @classmethod
    async def _assert_session_exists(cls, session_id: int, agent_type: str | None = None) -> AgentSession:
        session = await AgentSessionDao.get_session_by_id(session_id)
        if session is None:
            raise ServiceException(message='会话不存在')
        if agent_type and session.agent_type != agent_type:
            raise ServiceException(message='会话不存在')
        return session

    @classmethod
    @transactional(read_only=True)
    async def get_session_vo(cls, session_id: int, agent_type: str | None = None) -> AgentSessionVo:
        session = await cls._assert_session_exists(session_id, agent_type=agent_type)
        return cls._to_vo(session)

    @classmethod
    @transactional(read_only=True)
    async def get_session_list(
        cls,
        agent_type: str,
        user_id: int,
        title: str | None = None,
        is_page: bool = True,
        page_num: int = 1,
        page_size: int = 20,
        data_scope_sql: ColumnElement | None = None,
    ) -> PageModel[AgentSessionVo] | list[AgentSessionVo]:
        result = await AgentSessionDao.get_session_list(
            agent_type=agent_type,
            user_id=user_id,
            title=title,
            is_page=is_page,
            page_num=page_num,
            page_size=page_size,
            data_scope_sql=data_scope_sql,
        )
        return cls._to_vo_page(result)

    @classmethod
    @transactional()
    async def create_session(
        cls,
        agent_type: str,
        user_id: int,
        dept_id: int | None,
        create_by: str,
        session_title: str | None = None,
        model_id: int | None = None,
    ) -> AgentSessionVo:
        session = AgentSession(
            agent_type=agent_type,
            session_title=session_title or '新会话',
            status=SessionStatus.ACTIVE.value,
            model_id=model_id,
            user_id=user_id,
            dept_id=dept_id,
            create_by=create_by,
            update_by=create_by,
        )
        result = await AgentSessionDao.add_session(session)
        logger.info('[AgentSession] 创建会话: session_id={}, agent_type={}', result.session_id, agent_type)
        return cls._to_vo(result)

    @classmethod
    @transactional()
    async def rename_session(cls, session_id: int, session_title: str, update_by: str = '', agent_type: str | None = None) -> None:
        await cls._assert_session_exists(session_id, agent_type=agent_type)
        await AgentSessionDao.update_session_title(session_id, session_title, update_by=update_by)
        logger.info('[AgentSession] 重命名会话: session_id={}, title={}', session_id, session_title)

    @classmethod
    @transactional()
    async def close_session(cls, session_id: int, update_by: str = '', agent_type: str | None = None) -> None:
        await cls._assert_session_exists(session_id, agent_type=agent_type)
        await AgentSessionDao.update_session_status(session_id, SessionStatus.CLOSED.value, update_by=update_by)
        logger.info('[AgentSession] 关闭会话: session_id={}', session_id)

    @classmethod
    @transactional()
    async def delete_session(cls, session_id: int, update_by: str = '', agent_type: str | None = None) -> None:
        await cls._assert_session_exists(session_id, agent_type=agent_type)
        try:
            await Checkpointer.delete_thread(str(session_id))
        except Exception as e:
            logger.opt(exception=True).warning('[AgentSession] 清理 Checkpointer 失败，已忽略: session_id={}, err={}', session_id, e)
        await AgentSessionDao.soft_delete(session_id, update_by)
        await AgentMessageDao.soft_delete_by_session(session_id, update_by)
        logger.info('[AgentSession] 删除会话: session_id={}', session_id)
