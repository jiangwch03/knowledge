import threading
from typing import Optional

from knowledge_common.utils.log_util import logger
from langgraph.checkpoint.base import BaseCheckpointSaver
from knowledge_common.agent.memory.short_memory.redis_saver import RedisSaver


class Checkpointer:
    """
    LangGraph Checkpointer 单例管理

    以 session_id 为 thread_id 自动保存/恢复 Agent 状态快照，
    支持同一会话多轮对话上下文自动恢复，进程重启后不丢失。

    切换后端：修改 _init_instance 中的构建逻辑即可，业务层无感知。
    - Redis: AsyncRedisSaver（当前默认，支持持久化）
    - InMemory: InMemorySaver（开发/测试用，进程重启丢失）
    """
    _saver: Optional[BaseCheckpointSaver] = None
    _lock: threading.Lock = threading.Lock()

    @staticmethod
    async def init_checkpointer() -> None:
        """
        初始化 Checkpointer 单例（双重检查锁定，线程安全）

        在应用 lifespan 中 Redis 连接就绪后调用。
        """
        if Checkpointer._saver is None:
            with Checkpointer._lock:
                if Checkpointer._saver is None:
                    # ── 后端选择 ──────────────────────────────────────
                    # Redis（默认）：持久化，支持进程重启恢复（需 Redis Stack）
                    Checkpointer._saver = await RedisSaver.get_saver()

                    # InMemory（可选）：无需外部依赖，进程重启后记忆丢失
                    # from langgraph.checkpoint.memory import InMemorySaver
                    # Checkpointer._saver = InMemorySaver()

        logger.info('[Agent] LangGraph Checkpointer 初始化完成')

    @staticmethod
    async def get_checkpointer() -> BaseCheckpointSaver:
        """
        获取 Checkpointer 单例实例，未初始化时自动初始化

        业务方无需关心初始化时机，直接调用即可。

        :return: BaseCheckpointSaver 实例
        """
        if Checkpointer._saver is None:
            await Checkpointer.init_checkpointer()
        assert Checkpointer._saver is not None
        return Checkpointer._saver

    @staticmethod
    async def delete_thread(thread_id: str) -> None:
        """
        删除指定 thread_id 的全部 checkpoint 与中间写入数据

        说明：
        - 当前默认后端 AsyncRedisSaver 支持 adelete_thread
        - 若后端未实现该能力，记录日志并跳过，不抛错
        """
        saver = await Checkpointer.get_checkpointer()
        delete_fn = getattr(saver, 'adelete_thread', None)
        if delete_fn is None:
            logger.warning('[Agent] 当前 Checkpointer 不支持 adelete_thread，跳过清理: thread_id={}', thread_id)
            return
        await delete_fn(thread_id)
        logger.info('[Agent] 已清理 Checkpointer 线程数据: thread_id={}', thread_id)
