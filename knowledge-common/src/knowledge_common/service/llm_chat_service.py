"""
LLM Chat 服务

提供大模型驱动的通用聊天能力，支持：
- 根据参数ID创建专用 ChatModel
- 图片描述生成
- TXT 转 Markdown
"""

import base64

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from knowledge_common.common.factory.langchain_model_factory import LangChainModelFactory
from knowledge_common.config.prompt_config import prompt_config
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.langchain_model_vo import ChatModelConfigModel


class LlmChatService:
    """
    LLM Chat 服务

    提供大模型驱动的通用聊天能力，支持：
    - 根据参数ID创建 ChatModel
    - 图片描述生成
    - TXT 转 Markdown
    """

    TXT_MAX_BYTES = 512 * 1024

    @classmethod
    async def _create_chat_model(cls, param_id: str) -> Runnable | None:
        """
        根据参数ID查询模型适配配置并创建 ChatModel

        从 ai_model_function_adapter 表获取模型配置，通过 LangChainModelFactory
        创建 ChatModel 实例。未配置时返回 None，不抛异常。

        :param param_id: 参数ID，对应数据库中的 param_id 字段
        :return: ChatModel Runnable 实例，未配置时返回 None
        """
        adapter_config = await AiModelFunctionAdapterDao.get_adapter_by_param_id(param_id)
        if not adapter_config:
            logger.warning(f'未找到 {param_id} 模型适配配置')
            return None
        return LangChainModelFactory.create_chat_model(
            ChatModelConfigModel(
                model_code=adapter_config.model_code,
                provider=adapter_config.provider,
                api_key=adapter_config.api_key,
                base_url=adapter_config.base_url,
                temperature=adapter_config.temperature,
                max_tokens=adapter_config.max_tokens,
            )
        )

    @classmethod
    async def generate_image_description(cls, image_url: str) -> str:
        """
        调用大模型生成单张图片的描述文本

        内部自动创建 ChatModel，无需调用方管理模型生命周期。
        若模型未配置或调用失败，返回默认文本 'image' 并记录警告日志。

        :param image_url: 图片的可访问 URL（需为模型可访问的公网或内网地址）
        :return: 图片描述文本，失败时返回 'image'
        """
        chat_model = await cls._create_chat_model('md_image_description')
        if not chat_model:
            return 'image'

        try:
            system_prompt = prompt_config.get_system_prompt('md_image_description') or '请用一句话描述这张图片的内容。'
            message = HumanMessage(
                content=[
                    {'type': 'text', 'text': system_prompt},
                    {'type': 'image_url', 'image_url': {'url': image_url}},
                ]
            )
            resp = await chat_model.ainvoke([message])
            return str(resp.content).strip() or 'image'
        except Exception as e:
            logger.warning(f'图片描述生成失败: {e}')
            return 'image'

    @classmethod
    async def generate_image_description_from_bytes(cls, image_bytes: bytes, image_format: str = 'png') -> str:
        """调用大模型生成图片描述（通过 base64 编码直传，无需外部可访问 URL）

        适用于 LLM 无法直接访问 MinIO 等内部存储的场景。
        将图片字节编码为 data URI 后传入模型，无需额外的网络中转。

        :param image_bytes: 图片的完整二进制内容
        :param image_format: 图片格式后缀，如 'png', 'jpg', 'jpeg', 'gif', 'webp'，默认 'png'
        :return: 图片描述文本，失败时返回 'image'
        """
        chat_model = await cls._create_chat_model('md_image_description')
        if not chat_model:
            return 'image'

        try:
            b64_data = base64.b64encode(image_bytes).decode('utf-8')
            data_uri = f'data:image/{image_format};base64,{b64_data}'

            system_prompt = prompt_config.get_system_prompt('md_image_description') or '请用一句话描述这张图片的内容。'
            message = HumanMessage(
                content=[
                    {'type': 'text', 'text': system_prompt},
                    {'type': 'image_url', 'image_url': {'url': data_uri}},
                ]
            )
            resp = await chat_model.ainvoke([message])
            return str(resp.content).strip() or 'image'
        except Exception as e:
            logger.warning(f'图片描述生成失败: {e}')
            return 'image'

    @classmethod
    async def txt_to_markdown(cls, content: str) -> str:
        """
        TXT 转 Markdown

        根据 'txt_to_markdown' 参数ID获取模型配置和 system prompt，
        调用大模型将纯文本转换为 Markdown 格式。

        :param content: UTF-8 文本内容，大小不超过 512KB
        :return: Markdown 内容
        :raises ServiceException: 内容超限、未找到模型配置或提示词配置时抛出
        """
        if len(content.encode('utf-8')) > cls.TXT_MAX_BYTES:
            raise ServiceException('文本内容超过 512KB，请拆分后重试')

        chat_model = await cls._create_chat_model('txt_to_markdown')
        if not chat_model:
            raise ServiceException('未找到 txt_to_markdown 模型适配配置')

        system_prompt = prompt_config.get_system_prompt('txt_to_markdown')
        if not system_prompt:
            raise ServiceException('未找到 txt_to_markdown 提示词配置')

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=content),
        ]
        response = await chat_model.ainvoke(messages)
        return str(response.content)
