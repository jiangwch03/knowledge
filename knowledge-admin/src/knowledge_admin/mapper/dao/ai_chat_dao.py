from typing import Any

from knowledge_common.common.transactional import get_current_session
from sqlalchemy import select, update

from knowledge_admin.mapper.do.ai_chat_do import AiChatConfig
from knowledge_admin.vo.ai_chat_vo import AiChatConfigModel


class AiChatConfigDao:
    """
    AI对话配置数据库操作层
    """

    @classmethod
    async def get_chat_config_detail_by_user_id(cls, user_id: int) -> AiChatConfig | None:
        """
        根据用户ID获取配置

        :param user_id: 用户ID
        :return: 配置对象
        """
        db = get_current_session()
        ai_chat_config = (
            (await db.execute(select(AiChatConfig).where(AiChatConfig.user_id == user_id))).scalars().first()
        )

        return ai_chat_config

    @classmethod
    async def add_chat_config_dao(cls, chat_config: AiChatConfigModel) -> AiChatConfig:
        """
        新增对话配置数据库操作

        :param chat_config: 对话配置对象
        :return: 配置对象
        """
        db = get_current_session()
        db_chat_config = AiChatConfig(**chat_config.model_dump(exclude_unset=True))
        db.add(db_chat_config)
        await db.flush()

        return db_chat_config

    @classmethod
    async def edit_chat_config_dao(cls, chat_config: dict[str, Any]) -> None:
        """
        编辑对话配置数据库操作

        :param chat_config: 需要更新的对话配置字典
        :return:
        """
        db = get_current_session()
        await db.execute(update(AiChatConfig), [chat_config])
