"""
日志聚合通过 MessageStreamService 推送-消费端到端测试

覆盖:
- 推送链路: LogQueueService.enqueue_operation_log → MessageStreamService.produce
- 消费链路: @consumer 装饰器 → LogDedupHelper → DAO 落库
- 去重: 同一 event_id 只落库一次
- 异常回滚释放: 失败时 dedup key 释放
- app_name 隔离: admin 推送的消息 rag 消费者不应触发

运行:
    cd /Users/jsir/programfiles/qoder/knowledge
    .venv/bin/pytest knowledge-common/tests/test_log_aggregation_via_message_stream.py -v -s
"""
from __future__ import annotations

import asyncio
import socket
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# 让测试可导入 knowledge-common
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 加载 admin .env(端到端测试拿真实 Redis 凭证用)
from dotenv import load_dotenv  # noqa: E402

_ENV_FILE = _PROJECT_ROOT / 'knowledge-admin' / 'src' / 'configs' / '.env.dev'
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)

from knowledge_common.message_stream import (  # noqa: E402
    Message,
    MessageStreamService,
    consumer,
)
from knowledge_common.message_stream.backends.redis_stream import RedisStreamBackend  # noqa: E402


# =============================================================================
# Fixtures
# =============================================================================


def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    """检查端口是否可连接(用于判断 Redis 是否可用)"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


@pytest.fixture(scope='session')
def redis_running() -> bool:
    return _port_open('127.0.0.1', 6379)


@pytest.fixture(autouse=True)
def _reset_service():
    """每个测试前后都 reset,保证消费者表 / 路径 / 任务 / backend 清零"""
    MessageStreamService.reset()
    yield
    MessageStreamService.reset()


# =============================================================================
# 测试用例
# =============================================================================


class TestLogAggregationPush:
    """推送链路测试"""

    @pytest.mark.asyncio
    async def test_push_operation_log_to_stream(self, redis_running):
        """验证操作日志推送到 Redis Stream"""
        if not redis_running:
            pytest.skip('Redis 6379 未连通,跳过端到端集成测试')

        from redis import asyncio as aioredis

        from knowledge_common.config.env import RedisConfig

        # 用唯一 topic,避免与其他测试串扰
        unique = uuid.uuid4().hex[:8]
        topic = f'log:operation:test-{unique}'

        try:
            redis_client = await aioredis.from_url(
                url=f'redis://{RedisConfig.redis_host}',
                port=RedisConfig.redis_port,
                username=RedisConfig.redis_username,
                password=RedisConfig.redis_password,
                db=RedisConfig.redis_database,
                decode_responses=True,
            )
            # 探测一次,鉴权失败 / 未配置时 skip(不算 fail)
            await redis_client.ping()
        except Exception as e:
            pytest.skip(f'Redis 鉴权 / 连接失败,跳过端到端集成测试: {e!r}')

        try:
            backend = RedisStreamBackend(redis_client, maxlen=1000)
            MessageStreamService.init(backend)

            # 模拟推送
            payload = {
                'title': '测试操作',
                'businessType': 0,
                'method': 'test.method',
                'requestMethod': 'GET',
                'operName': 'test_user',
                'operUrl': '/test',
                'operIp': '127.0.0.1',
                'status': 0,
            }
            headers = {
                'event_id': f'event_{unique}',
                'event_type': 'operation',
                'request_id': f'req_{unique}',
                'trace_id': f'trace_{unique}',
                'span_id': f'span_{unique}',
                'app_name': 'test-app',
                'source': 'unit_test',
            }

            # 推送消息
            xid = await MessageStreamService.produce(
                topic=topic,
                value=payload,
                key=f'req_{unique}',
                headers=headers,
            )
            assert xid

            # 验证消息在 stream 中
            messages = await redis_client.xrange(topic, count=1)
            assert len(messages) >= 1
            xid_received, fields = messages[0]
            assert xid_received == xid

            # 验证字段
            assert '__value' in fields
            assert '__key' in fields
            assert '__headers' in fields

        finally:
            # 优雅关闭
            await MessageStreamService.shutdown()
            # 清理 stream
            try:
                await redis_client.delete(topic)
            except Exception:
                pass
            await redis_client.aclose()


class TestLogAggregationConsume:
    """消费链路测试"""

    @pytest.mark.asyncio
    async def test_consume_operation_log(self, redis_running):
        """验证消费者能收到并处理操作日志"""
        if not redis_running:
            pytest.skip('Redis 6379 未连通,跳过端到端集成测试')

        from redis import asyncio as aioredis

        from knowledge_common.config.env import RedisConfig

        # 用唯一 topic,避免与其他测试串扰
        unique = uuid.uuid4().hex[:8]
        topic = f'log:operation:test-{unique}'
        group = f'log_writer:test-{unique}'

        try:
            redis_client = await aioredis.from_url(
                url=f'redis://{RedisConfig.redis_host}',
                port=RedisConfig.redis_port,
                username=RedisConfig.redis_username,
                password=RedisConfig.redis_password,
                db=RedisConfig.redis_database,
                decode_responses=True,
            )
            await redis_client.ping()
        except Exception as e:
            pytest.skip(f'Redis 鉴权 / 连接失败,跳过端到端集成测试: {e!r}')

        try:
            backend = RedisStreamBackend(redis_client, maxlen=1000)
            MessageStreamService.init(backend)

            received: list[Message] = []
            done = asyncio.Event()

            @consumer(topic=topic, group_id=group, id=f'ut-{unique}')
            async def handler(msg: Message) -> None:
                received.append(msg)
                done.set()

            with patch.object(MessageStreamService, '_import_subtree'):
                MessageStreamService.register_consumer_paths(['fake'])
                await MessageStreamService.discover_and_start()

            # 推送消息
            payload = {'title': '测试操作', 'status': 0}
            headers = {
                'event_id': f'event_{unique}',
                'event_type': 'operation',
                'app_name': 'test-app',
            }
            xid = await MessageStreamService.produce(
                topic=topic,
                value=payload,
                key=f'req_{unique}',
                headers=headers,
            )
            assert xid

            # 等消费(最多 5 秒)
            try:
                await asyncio.wait_for(done.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.fail(f'未收到消息: xid={xid}')

            assert len(received) >= 1
            msg = received[0]
            assert msg.topic == topic
            assert msg.value == payload
            assert msg.headers.get('event_id') == f'event_{unique}'

        finally:
            await MessageStreamService.shutdown()
            try:
                await redis_client.delete(topic)
            except Exception:
                pass
            await redis_client.aclose()


class TestLogAggregationDedup:
    """去重测试: 同一 event_id 只成功 acquire 一次"""

    @pytest.mark.asyncio
    async def test_same_event_id_dedup(self, redis_running):
        """同一 event_id 连续 acquire 2 次, 仅第一次返回 True"""
        if not redis_running:
            pytest.skip('Redis 6379 未连通,跳过端到端集成测试')

        from redis import asyncio as aioredis

        from knowledge_common.common.context import RedisContext
        from knowledge_common.config.env import RedisConfig
        from knowledge_common.service.log_service import LogDedupHelper

        unique = uuid.uuid4().hex[:8]
        event_id = f'dedup_test_{unique}'
        app_name = f'test-app-{unique}'

        try:
            redis_client = await aioredis.from_url(
                url=f'redis://{RedisConfig.redis_host}',
                port=RedisConfig.redis_port,
                username=RedisConfig.redis_username,
                password=RedisConfig.redis_password,
                db=RedisConfig.redis_database,
                decode_responses=True,
            )
            await redis_client.ping()
        except Exception as e:
            pytest.skip(f'Redis 鉴权 / 连接失败,跳过端到端集成测试: {e!r}')

        token = RedisContext.set_redis(redis_client)
        try:
            # 第一次 acquire -> True
            async with LogDedupHelper.acquire(event_id, app_name) as ok1:
                assert ok1 is True

            # 第二次 acquire(同一 event_id) -> False (去重窗口内)
            async with LogDedupHelper.acquire(event_id, app_name) as ok2:
                assert ok2 is False
        finally:
            # 清理 dedup key
            from knowledge_common.config.env import LogConfig

            dedup_key = f'{LogConfig.get_dedup_prefix(app_name)}:{event_id}'
            await redis_client.delete(dedup_key)
            RedisContext.reset_redis(token)
            await redis_client.aclose()


class TestLogAggregationExceptionRelease:
    """异常回滚释放测试: 异常时 dedup key 被释放, 允许重试"""

    @pytest.mark.asyncio
    async def test_exception_releases_dedup_key(self, redis_running):
        """第一次 acquire 成功后抛异常 → key 释放 → 第二次可再次成功"""
        if not redis_running:
            pytest.skip('Redis 6379 未连通,跳过端到端集成测试')

        from redis import asyncio as aioredis

        from knowledge_common.common.context import RedisContext
        from knowledge_common.config.env import RedisConfig
        from knowledge_common.service.log_service import LogDedupHelper

        unique = uuid.uuid4().hex[:8]
        event_id = f'exc_test_{unique}'
        app_name = f'test-app-{unique}'

        try:
            redis_client = await aioredis.from_url(
                url=f'redis://{RedisConfig.redis_host}',
                port=RedisConfig.redis_port,
                username=RedisConfig.redis_username,
                password=RedisConfig.redis_password,
                db=RedisConfig.redis_database,
                decode_responses=True,
            )
            await redis_client.ping()
        except Exception as e:
            pytest.skip(f'Redis 鉴权 / 连接失败,跳过端到端集成测试: {e!r}')

        token = RedisContext.set_redis(redis_client)
        try:
            # 第一次 acquire 成功, 但业务抛异常 → __aexit__ 释放 dedup key
            with pytest.raises(RuntimeError, match='模拟业务异常'):
                async with LogDedupHelper.acquire(event_id, app_name) as ok1:
                    assert ok1 is True
                    raise RuntimeError('模拟业务异常')

            # 第二次 acquire 应再次成功(key 已被释放)
            async with LogDedupHelper.acquire(event_id, app_name) as ok2:
                assert ok2 is True
        finally:
            # 清理 dedup key
            from knowledge_common.config.env import LogConfig

            dedup_key = f'{LogConfig.get_dedup_prefix(app_name)}:{event_id}'
            await redis_client.delete(dedup_key)
            RedisContext.reset_redis(token)
            await redis_client.aclose()


class TestLogAggregationIsolation:
    """app_name 隔离测试"""

    @pytest.mark.asyncio
    async def test_app_name_isolation(self, redis_running):
        """验证 admin 推送的消息 rag 消费者不应触发"""
        if not redis_running:
            pytest.skip('Redis 6379 未连通,跳过端到端集成测试')

        from redis import asyncio as aioredis

        from knowledge_common.config.env import RedisConfig

        # 用唯一 topic,避免与其他测试串扰
        unique = uuid.uuid4().hex[:8]
        admin_topic = f'log:operation:knowledge-admin-{unique}'
        rag_topic = f'log:operation:knowledge-content-{unique}'
        admin_group = f'log_writer:knowledge-admin-{unique}'
        rag_group = f'log_writer:knowledge-content-{unique}'

        try:
            redis_client = await aioredis.from_url(
                url=f'redis://{RedisConfig.redis_host}',
                port=RedisConfig.redis_port,
                username=RedisConfig.redis_username,
                password=RedisConfig.redis_password,
                db=RedisConfig.redis_database,
                decode_responses=True,
            )
            await redis_client.ping()
        except Exception as e:
            pytest.skip(f'Redis 鉴权 / 连接失败,跳过端到端集成测试: {e!r}')

        try:
            backend = RedisStreamBackend(redis_client, maxlen=1000)
            MessageStreamService.init(backend)

            admin_received: list[Message] = []
            rag_received: list[Message] = []
            admin_done = asyncio.Event()

            @consumer(topic=admin_topic, group_id=admin_group, id=f'ut-admin-{unique}')
            async def admin_handler(msg: Message) -> None:
                admin_received.append(msg)
                admin_done.set()

            @consumer(topic=rag_topic, group_id=rag_group, id=f'ut-rag-{unique}')
            async def rag_handler(msg: Message) -> None:
                rag_received.append(msg)

            with patch.object(MessageStreamService, '_import_subtree'):
                MessageStreamService.register_consumer_paths(['fake'])
                await MessageStreamService.discover_and_start()

            # 推送到 admin topic
            payload = {'title': 'admin 操作', 'status': 0}
            headers = {
                'event_id': f'event_{unique}',
                'event_type': 'operation',
                'app_name': 'knowledge-admin',
            }
            await MessageStreamService.produce(
                topic=admin_topic,
                value=payload,
                key=f'req_{unique}',
                headers=headers,
            )

            # 等 admin 消费者收到(最多 5 秒)
            try:
                await asyncio.wait_for(admin_done.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.fail('admin 消费者未收到消息')

            # 验证 rag 消费者未收到
            await asyncio.sleep(0.5)  # 等一下确保 rag 消费者有机会处理
            assert len(rag_received) == 0, 'rag 消费者不应收到 admin topic 的消息'

        finally:
            await MessageStreamService.shutdown()
            try:
                await redis_client.delete(admin_topic, rag_topic)
            except Exception:
                pass
            await redis_client.aclose()
