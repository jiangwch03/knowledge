"""
消息流服务单元 / 集成测试套件

覆盖 openspec/changes/message-stream-service-kafka-style-api/tasks.md 中:
- 6.2 端到端:produce → consume → ack
- 6.3 shutdown 优雅退出
- 6.4 reset 可多次跑
- 6.5 重试用完抛 MessageStreamError
- 7.1 Message 数据类
- 7.2 MessageStreamError
- 7.3 RedisStreamBackend(AsyncMock 协议层 + 真 Redis 集成)
- 7.4 @consumer 装饰器
- 7.5 produce 重试
- 7.6 discover_and_start 扫描
- 7.7 真 Redis 端到端

分层:
- ✅ 静态/Mock 层:不依赖 Redis,可任意环境跑通
- ⚠️ 真 Redis 集成层:6379 端口未连通时自动 skip

运行:
    cd /Users/jsir/programfiles/qoder/knowledge
    .venv/bin/pytest knowledge-common/tests/test_message_stream.py -v -s
"""
from __future__ import annotations

import asyncio
import json
import socket
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
    ConsumerInfo,
    Message,
    MessageStreamError,
    MessageStreamService,
    consumer,
)
from knowledge_common.message_stream.backends.base import StreamBackend  # noqa: E402
from knowledge_common.message_stream.backends.redis_stream import (  # noqa: E402
    RedisStreamBackend,
    _decode_field_headers,
    _decode_field_value,
    _encode_field_headers,
    _encode_field_value,
    _parse_stream_xid_timestamp,
)


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
# 7.1 Message 数据类
# =============================================================================


class Test71Message:
    """Message 数据类:字段访问、别名、默认值"""

    def test_default_values(self):
        msg = Message(topic='t1')
        assert msg.topic == 't1'
        assert msg.key is None
        assert msg.value is None
        assert msg.headers == {}
        assert msg.timestamp == 0
        assert msg.offset == ''
        assert msg.partition is None

    def test_field_access(self):
        msg = Message(
            topic='log:op',
            key='doc_1',
            value={'k': 'v'},
            headers={'h': 1},
            timestamp=1234,
            offset='1700000000000-0',
            partition=2,
        )
        assert msg.topic == 'log:op'
        assert msg.key == 'doc_1'
        assert msg.value == {'k': 'v'}
        assert msg.headers == {'h': 1}
        assert msg.timestamp == 1234
        assert msg.offset == '1700000000000-0'
        assert msg.partition == 2

    def test_stream_payload_aliases(self):
        """msg.stream ≡ msg.topic,msg.payload ≡ msg.value"""
        msg = Message(topic='t1', value={'k': 'v'})
        assert msg.stream == 't1'
        assert msg.stream == msg.topic
        assert msg.payload == {'k': 'v'}
        assert msg.payload == msg.value

    def test_repr_contains_keys(self):
        msg = Message(topic='t', key='k', offset='1-0', timestamp=99)
        s = repr(msg)
        assert 't' in s
        assert 'k' in s
        assert '1-0' in s


# =============================================================================
# 7.2 MessageStreamError
# =============================================================================


class Test72MessageStreamError:
    """MessageStreamError 异常信息 / 上下文属性"""

    def test_basic_message(self):
        e = MessageStreamError('boom')
        assert str(e) == 'boom'
        assert e.topic is None
        assert e.cause is None

    def test_with_topic(self):
        e = MessageStreamError('boom', topic='log:op')
        assert '[log:op]' in str(e)
        assert 'boom' in str(e)
        assert e.topic == 'log:op'

    def test_with_cause(self):
        cause = ValueError('inner')
        e = MessageStreamError('outer', topic='t', cause=cause)
        s = str(e)
        assert 'outer' in s
        assert 'inner' in s
        assert e.cause is cause

    def test_is_exception_subclass(self):
        assert issubclass(MessageStreamError, Exception)


# =============================================================================
# 7.3 RedisStreamBackend(AsyncMock 协议层 + 真 Redis 集成)
# =============================================================================


class Test73aRedisStreamBackendUnit:
    """RedisStreamBackend 协议层单元测试(AsyncMock,不依赖真 Redis)"""

    @pytest.mark.asyncio
    async def test_publish_calls_xadd_and_returns_xid(self):
        mock_redis = MagicMock()
        mock_redis.xadd = AsyncMock(return_value='1700000000000-0')
        backend = RedisStreamBackend(mock_redis, maxlen=999)

        xid = await backend.publish('t1', {'k': 'v'}, key='K', headers={'h': 1})

        assert xid == '1700000000000-0'
        mock_redis.xadd.assert_awaited_once()
        kwargs = mock_redis.xadd.await_args.kwargs
        assert kwargs['name'] == 't1'
        assert kwargs['maxlen'] == 999
        assert kwargs['approximate'] is True
        fields = kwargs['fields']
        assert fields['__value'] == json.dumps({'k': 'v'}, ensure_ascii=False)
        assert fields['__key'] == 'K'
        assert json.loads(fields['__headers']) == {'h': 1}

    @pytest.mark.asyncio
    async def test_publish_string_value_no_json(self):
        mock_redis = MagicMock()
        mock_redis.xadd = AsyncMock(return_value='1-0')
        backend = RedisStreamBackend(mock_redis)

        await backend.publish('t', 'plain', key=None, headers=None)

        fields = mock_redis.xadd.await_args.kwargs['fields']
        assert fields['__value'] == 'plain'
        assert '__key' not in fields
        assert '__headers' not in fields

    @pytest.mark.asyncio
    async def test_publish_wraps_connection_error(self):
        from redis.exceptions import ConnectionError as RedisConnectionError
        mock_redis = MagicMock()
        mock_redis.xadd = AsyncMock(side_effect=RedisConnectionError('down'))
        backend = RedisStreamBackend(mock_redis)

        with pytest.raises(MessageStreamError) as exc_info:
            await backend.publish('t', 'v', None, None)
        assert exc_info.value.topic == 't'
        assert isinstance(exc_info.value.cause, RedisConnectionError)

    @pytest.mark.asyncio
    async def test_consume_parses_messages(self):
        mock_redis = MagicMock()
        # xreadgroup 返回:[[topic, [(xid, fields), ...]]]
        mock_redis.xreadgroup = AsyncMock(return_value=[
            ['t1', [
                ('1700000000000-0', {
                    '__value': '{"k": "v"}',
                    '__key': 'K',
                    '__headers': '{"h": 1}',
                }),
                ('1700000000001-0', {'__value': 'plain'}),
            ]]
        ])
        backend = RedisStreamBackend(mock_redis)

        msgs = await backend.consume('t1', 'g1', 'c1', block_ms=100, count=10)

        assert len(msgs) == 2
        assert msgs[0].topic == 't1'
        assert msgs[0].key == 'K'
        assert msgs[0].value == {'k': 'v'}
        assert msgs[0].headers == {'h': 1}
        assert msgs[0].timestamp == 1700000000000
        assert msgs[0].offset == '1700000000000-0'
        assert msgs[0].partition is None
        assert msgs[1].value == 'plain'
        assert msgs[1].key is None
        assert msgs[1].headers == {}

    @pytest.mark.asyncio
    async def test_consume_empty_response_returns_empty(self):
        mock_redis = MagicMock()
        mock_redis.xreadgroup = AsyncMock(return_value=None)
        backend = RedisStreamBackend(mock_redis)

        msgs = await backend.consume('t', 'g', 'c', 100, 10)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_ack_returns_count(self):
        mock_redis = MagicMock()
        mock_redis.xack = AsyncMock(return_value=2)
        backend = RedisStreamBackend(mock_redis)

        n = await backend.ack('t', 'g', '1-0', '2-0')
        assert n == 2
        mock_redis.xack.assert_awaited_once_with('t', 'g', '1-0', '2-0')

    @pytest.mark.asyncio
    async def test_ack_empty_offsets_returns_zero(self):
        mock_redis = MagicMock()
        mock_redis.xack = AsyncMock(return_value=0)
        backend = RedisStreamBackend(mock_redis)

        n = await backend.ack('t', 'g')
        assert n == 0
        mock_redis.xack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_group_busygroup_is_idempotent(self):
        from redis.exceptions import ResponseError
        mock_redis = MagicMock()
        mock_redis.xgroup_create = AsyncMock(
            side_effect=ResponseError('BUSYGROUP Consumer Group name already exists')
        )
        backend = RedisStreamBackend(mock_redis)

        # 不应抛异常,而是吞掉 BUSYGROUP
        await backend.create_group('t', 'g')

    @pytest.mark.asyncio
    async def test_create_group_other_error_raises(self):
        from redis.exceptions import ResponseError
        mock_redis = MagicMock()
        mock_redis.xgroup_create = AsyncMock(side_effect=ResponseError('NOGROUP'))
        backend = RedisStreamBackend(mock_redis)

        with pytest.raises(MessageStreamError):
            await backend.create_group('t', 'g')

    @pytest.mark.asyncio
    async def test_claim_idle_parses_response(self):
        mock_redis = MagicMock()
        # xautoclaim 返回:[next_cursor, [(xid, fields), ...], deleted_ids]
        mock_redis.xautoclaim = AsyncMock(return_value=[
            '0-0',
            [('1-0', {'__value': 'v1'})],
            [],
        ])
        backend = RedisStreamBackend(mock_redis)

        msgs = await backend.claim_idle('t', 'g', 'c', min_idle_ms=1000)
        assert len(msgs) == 1
        assert msgs[0].value == 'v1'
        assert msgs[0].offset == '1-0'

    @pytest.mark.asyncio
    async def test_claim_idle_empty_response(self):
        mock_redis = MagicMock()
        mock_redis.xautoclaim = AsyncMock(return_value=['0-0', [], []])
        backend = RedisStreamBackend(mock_redis)

        msgs = await backend.claim_idle('t', 'g', 'c', 1000)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_shutdown_clears_reference(self):
        mock_redis = MagicMock()
        backend = RedisStreamBackend(mock_redis)
        assert backend._redis is mock_redis
        await backend.shutdown()
        assert backend._redis is None


class Test73bFieldEncoders:
    """字段编解码辅助函数"""

    def test_encode_decode_value_dict(self):
        raw = _encode_field_value({'k': 'v', 'n': 1})
        assert _decode_field_value(raw) == {'k': 'v', 'n': 1}

    def test_encode_decode_value_list(self):
        raw = _encode_field_value([1, 2, 3])
        assert _decode_field_value(raw) == [1, 2, 3]

    def test_encode_decode_value_str(self):
        raw = _encode_field_value('hello')
        assert raw == 'hello'
        assert _decode_field_value(raw) == 'hello'

    def test_decode_value_empty(self):
        assert _decode_field_value('') is None

    def test_encode_decode_headers(self):
        raw = _encode_field_headers({'a': 1})
        assert _decode_field_headers(raw) == {'a': 1}

    def test_decode_headers_empty(self):
        assert _decode_field_headers(None) == {}
        assert _decode_field_headers('') == {}

    def test_parse_xid_timestamp(self):
        assert _parse_stream_xid_timestamp('1700000000000-0') == 1700000000000
        assert _parse_stream_xid_timestamp('bad-format') == 0


# =============================================================================
# 7.4 @consumer 装饰器
# =============================================================================


class Test74Consumer:
    """@consumer 装饰器:基本注册、参数透传、去重"""

    def test_basic_registration(self):
        @consumer(topic='t1', group_id='g1')
        async def handler(msg):
            pass

        # 注册键 = `{module}.{func_name}`
        key = f'{handler.__module__}.handler'
        assert key in MessageStreamService._consumers
        info = MessageStreamService._consumers[key]
        assert info.topic == 't1'
        assert info.group_id == 'g1'
        assert info.handler is handler
        assert info.on_error == 'retry'
        assert info.max_retries == 3
        assert info.business_id_fn is None

    def test_custom_id_overrides_default(self):
        @consumer(topic='t', group_id='g', id='my-custom-id')
        async def h(msg):
            pass

        assert 'my-custom-id' in MessageStreamService._consumers
        # 默认 `{module}.h` 不应再被注册
        assert f'{h.__module__}.h' not in MessageStreamService._consumers

    def test_all_params_pass_through(self):
        bid = lambda msg: msg.value['doc_id']  # noqa: E731

        @consumer(
            topic='t', group_id='g', id='full',
            business_id_fn=bid, on_error='rethrow', max_retries=7,
        )
        async def h(msg):
            pass

        info = MessageStreamService._consumers['full']
        assert info.business_id_fn is bid
        assert info.on_error == 'rethrow'
        assert info.max_retries == 7

    def test_duplicate_registration_skipped(self):
        @consumer(topic='t', group_id='g', id='dup')
        async def h1(msg):
            pass

        # 同 id 再注册一次,应跳过(不抛异常,_consumers 数量不增)
        before = len(MessageStreamService._consumers)

        @consumer(topic='t', group_id='g', id='dup')
        async def h2(msg):
            pass

        after = len(MessageStreamService._consumers)
        assert before == after
        # 原 handler 仍然是 h1,不被 h2 覆盖
        assert MessageStreamService._consumers['dup'].handler is h1

    def test_decorator_returns_original_function(self):
        async def orig(msg):
            return 'x'

        decorated = consumer(topic='t', group_id='g')(orig)
        assert decorated is orig


# =============================================================================
# 7.5 MessageStreamService.produce(成功 / 重试 / 失败)
# =============================================================================


class _StubBackend(StreamBackend):
    """测试用最小后端:publish 可控成功/失败"""

    def __init__(self, *, fail_times: int = 0, raise_unknown: bool = False):
        self.fail_times = fail_times
        self.raise_unknown = raise_unknown
        self.publish_calls = 0

    async def publish(self, topic, value, key, headers):
        self.publish_calls += 1
        if self.publish_calls <= self.fail_times:
            if self.raise_unknown:
                raise RuntimeError('unknown failure')
            raise MessageStreamError('backend fail', topic=topic)
        return f'fakeid-{self.publish_calls}'

    async def consume(self, topic, group_id, consumer_id, block_ms, count):
        return []

    async def ack(self, topic, group_id, *msg_offsets):
        return len(msg_offsets)

    async def create_group(self, topic, group_id):
        return None

    async def claim_idle(self, topic, group_id, consumer_id, min_idle_ms):
        return []

    async def shutdown(self):
        return None


class Test75Produce:
    """produce:成功 / 重试 / 最终失败抛 MessageStreamError"""

    @pytest.mark.asyncio
    async def test_produce_success_first_try(self):
        backend = _StubBackend(fail_times=0)
        MessageStreamService.init(backend)

        xid = await MessageStreamService.produce('t', {'k': 'v'})
        assert xid == 'fakeid-1'
        assert backend.publish_calls == 1

    @pytest.mark.asyncio
    async def test_produce_recovers_after_retries(self):
        backend = _StubBackend(fail_times=2)
        MessageStreamService.init(backend)

        xid = await MessageStreamService.produce(
            't', 'v', max_retries=5, retry_interval=0.01,
        )
        assert xid == 'fakeid-3'
        assert backend.publish_calls == 3

    @pytest.mark.asyncio
    async def test_produce_exhausted_raises(self):
        backend = _StubBackend(fail_times=10)
        MessageStreamService.init(backend)

        with pytest.raises(MessageStreamError) as exc_info:
            await MessageStreamService.produce(
                't', 'v', max_retries=3, retry_interval=0.01,
            )
        # 实际尝试 3 次
        assert backend.publish_calls == 3
        assert exc_info.value.topic == 't'

    @pytest.mark.asyncio
    async def test_produce_wraps_unknown_exception(self):
        backend = _StubBackend(fail_times=10, raise_unknown=True)
        MessageStreamService.init(backend)

        with pytest.raises(MessageStreamError):
            await MessageStreamService.produce(
                't', 'v', max_retries=2, retry_interval=0.01,
            )
        assert backend.publish_calls == 2

    @pytest.mark.asyncio
    async def test_produce_without_init_raises(self):
        # reset 已清空 _backend
        with pytest.raises(MessageStreamError):
            await MessageStreamService.produce('t', 'v')


# =============================================================================
# 7.6 discover_and_start 模拟扫描 + 注册
# =============================================================================


class Test76DiscoverAndStart:
    """discover_and_start:扫描路径 + 拉起后台协程"""

    @pytest.mark.asyncio
    async def test_no_backend_raises(self):
        with pytest.raises(MessageStreamError):
            await MessageStreamService.discover_and_start()

    @pytest.mark.asyncio
    async def test_no_scan_paths_warns_but_no_raise(self, caplog):
        backend = _StubBackend()
        MessageStreamService.init(backend)
        # 不调 register_consumer_paths
        await MessageStreamService.discover_and_start()
        # 没有 consumer,_tasks 应为空
        assert MessageStreamService._tasks == {}

    @pytest.mark.asyncio
    async def test_register_paths_deduplicates(self):
        MessageStreamService.register_consumer_paths(['a.b', 'a.b', 'c.d'])
        MessageStreamService.register_consumer_paths(['c.d', 'e.f'])
        # 累加 + 去重
        assert MessageStreamService._scan_paths == ['a.b', 'c.d', 'e.f']

    @pytest.mark.asyncio
    async def test_discover_starts_registered_consumers(self):
        """模拟:手动写入 _consumers,验证 discover 会为每个 consumer 拉起 task"""
        backend = _StubBackend()
        MessageStreamService.init(backend)

        called = asyncio.Event()

        async def handler(msg):
            called.set()

        info = ConsumerInfo(
            consumer_id='ut.h1', topic='t1', group_id='g1', handler=handler,
        )
        MessageStreamService._consumers['ut.h1'] = info
        # 用 patch 跳过 _import_subtree(避免真去 import)
        with patch.object(MessageStreamService, '_import_subtree'):
            MessageStreamService.register_consumer_paths(['fake.path'])
            await MessageStreamService.discover_and_start()

        # 验证后台协程已拉起
        assert 'ut.h1' in MessageStreamService._tasks
        assert not MessageStreamService._tasks['ut.h1'].done()
        # 清理
        await MessageStreamService.shutdown()


# =============================================================================
# 6.3 / 6.4 shutdown 优雅退出 + reset 可多次跑
# =============================================================================


class Test63Shutdown:
    @pytest.mark.asyncio
    async def test_shutdown_cancels_tasks(self):
        backend = _StubBackend()
        MessageStreamService.init(backend)

        async def handler(msg):
            pass

        info = ConsumerInfo(
            consumer_id='ut.h', topic='t', group_id='g', handler=handler,
        )
        MessageStreamService._consumers['ut.h'] = info

        with patch.object(MessageStreamService, '_import_subtree'):
            MessageStreamService.register_consumer_paths(['x'])
            await MessageStreamService.discover_and_start()

        task = MessageStreamService._tasks['ut.h']
        assert not task.done()

        await MessageStreamService.shutdown()

        # 关闭后 task 已被取消 / 完成
        assert task.done()
        assert MessageStreamService._tasks == {}
        assert MessageStreamService._claim_tasks == {}


class Test64Reset:
    @pytest.mark.asyncio
    async def test_reset_clears_state_and_can_repeat(self):
        backend = _StubBackend()
        MessageStreamService.init(backend)
        MessageStreamService._consumers['x'] = ConsumerInfo(
            consumer_id='x', topic='t', group_id='g', handler=AsyncMock(),
        )
        MessageStreamService.register_consumer_paths(['p1'])

        MessageStreamService.reset()
        assert MessageStreamService._backend is None
        assert MessageStreamService._consumers == {}
        assert MessageStreamService._scan_paths == []
        assert MessageStreamService._tasks == {}
        assert MessageStreamService._claim_tasks == {}

        # 再次 init + register + reset,不应抛异常
        MessageStreamService.init(_StubBackend())
        MessageStreamService.register_consumer_paths(['p2'])
        MessageStreamService.reset()
        assert MessageStreamService._scan_paths == []


# =============================================================================
# 6.5 重试:故意失败 3 次确认抛 MessageStreamError
# =============================================================================


class Test65RetryExhausted:
    @pytest.mark.asyncio
    async def test_three_failures_raise(self):
        backend = _StubBackend(fail_times=3)
        MessageStreamService.init(backend)

        with pytest.raises(MessageStreamError):
            await MessageStreamService.produce(
                't', 'v', max_retries=3, retry_interval=0.01,
            )
        assert backend.publish_calls == 3


# =============================================================================
# 6.2 / 7.7 端到端集成测试(真 Redis,不可用时 skip)
# =============================================================================


class Test77EndToEndRealRedis:
    """真 Redis 端到端:produce → consume → ack 全链路"""

    @pytest.mark.asyncio
    async def test_end_to_end_produce_consume_ack(self, redis_running):
        if not redis_running:
            pytest.skip('Redis 6379 未连通,跳过端到端集成测试')

        from redis import asyncio as aioredis

        from knowledge_common.config.env import RedisConfig

        # 用唯一 topic / group,避免与其他测试串扰
        unique = uuid.uuid4().hex[:8]
        topic = f'msg-stream-ut:e2e:{unique}'
        group = f'g-{unique}'

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

            received: list[Message] = []
            done = asyncio.Event()

            @consumer(topic=topic, group_id=group, id=f'ut-{unique}')
            async def handler(msg: Message) -> None:
                received.append(msg)
                done.set()

            with patch.object(MessageStreamService, '_import_subtree'):
                MessageStreamService.register_consumer_paths(['fake'])
                await MessageStreamService.discover_and_start()

            # 推送一条消息
            xid = await MessageStreamService.produce(
                topic, {'k': 'v', 'n': 42}, key='doc_1', headers={'h': 'x'},
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
            assert msg.value == {'k': 'v', 'n': 42}
            assert msg.key == 'doc_1'
            assert msg.headers == {'h': 'x'}
            assert msg.offset == xid

            # 等 ack 落地
            await asyncio.sleep(0.2)
            # 验证 PEL 已清空(ack 成功)
            pending = await redis_client.xpending(topic, group)
            assert pending['pending'] == 0, f'PEL 未清空: {pending}'

        finally:
            # 优雅关闭
            await MessageStreamService.shutdown()
            # 清理 stream
            try:
                await redis_client.delete(topic)
            except Exception:
                pass
            await redis_client.aclose()


# =============================================================================
# 7.8 后端工厂(create_backend)与 init_from_settings
# =============================================================================


class TestFactoryCreateBackend:
    """backends/factory.py create_backend: .env 选 redis / kafka 后端"""

    def test_redis_backend_creates_redis_stream_backend(self):
        from knowledge_common.message_stream.backends.factory import create_backend

        mock_redis = MagicMock(name='mock_redis')
        settings = SimpleNamespace(
            message_stream_backend='redis',
            message_stream_redis_maxlen=8888,
        )
        backend = create_backend(settings, redis=mock_redis)
        assert isinstance(backend, RedisStreamBackend)
        # 验证 maxlen 透传
        assert backend._maxlen == 8888
        assert backend._redis is mock_redis

    def test_redis_backend_without_redis_raises(self):
        from knowledge_common.message_stream.backends.factory import create_backend

        settings = SimpleNamespace(
            message_stream_backend='redis',
            message_stream_redis_maxlen=100000,
        )
        with pytest.raises(MessageStreamError) as exc_info:
            create_backend(settings, redis=None)
        assert 'Redis 后端需要注入 redis 客户端' in str(exc_info.value)

    def test_kafka_backend_creates_kafka_stream_backend(self):
        from knowledge_common.message_stream.backends.factory import create_backend

        settings = SimpleNamespace(
            message_stream_backend='kafka',
            message_stream_kafka_bootstrap_servers='broker1:9092,broker2:9092',
            message_stream_kafka_client_id='ut-client',
            message_stream_kafka_security_protocol='PLAINTEXT',
            message_stream_kafka_sasl_mechanism='',
            message_stream_kafka_sasl_username='',
            message_stream_kafka_sasl_password='',
            message_stream_kafka_acks='1',
            message_stream_kafka_linger_ms=10,
            message_stream_kafka_request_timeout_ms=15000,
            message_stream_kafka_session_timeout_ms=20000,
            message_stream_kafka_heartbeat_interval_ms=5000,
            message_stream_kafka_auto_offset_reset='latest',
            message_stream_kafka_create_topic_partitions=3,
            message_stream_kafka_create_topic_replication_factor=2,
        )
        # aiokafka 未装时 skip，不计 fail
        try:
            from knowledge_common.message_stream.backends.kafka_stream import KafkaStreamBackend  # noqa: F401
        except ImportError:
            pytest.skip('aiokafka 未安装,跳过 Kafka 后端工厂测试')

        backend = create_backend(settings, redis=None)
        assert isinstance(backend, KafkaStreamBackend)
        assert backend._bootstrap_servers == 'broker1:9092,broker2:9092'
        assert backend._client_id == 'ut-client'
        assert backend._acks == '1'
        assert backend._linger_ms == 10
        assert backend._auto_offset_reset == 'latest'
        assert backend._create_topic_partitions == 3
        assert backend._create_topic_replication_factor == 2

    def test_unknown_backend_raises(self):
        from knowledge_common.message_stream.backends.factory import create_backend

        settings = SimpleNamespace(
            message_stream_backend='rocketmq',  # 未支持的后端
            message_stream_redis_maxlen=100000,
        )
        with pytest.raises(MessageStreamError) as exc_info:
            create_backend(settings, redis=MagicMock())
        assert '未知消息流后端类型' in str(exc_info.value)
        assert 'rocketmq' in str(exc_info.value)


class TestInitFromSettings:
    """MessageStreamService.init_from_settings: 一行调用 = init + 工厂"""

    def test_redis_path_injects_backend(self):
        settings = SimpleNamespace(
            message_stream_backend='redis',
            message_stream_redis_maxlen=5000,
        )
        mock_redis = MagicMock(name='mock_redis')
        backend = MessageStreamService.init_from_settings(settings, redis=mock_redis)
        assert isinstance(backend, RedisStreamBackend)
        # 验证 _backend 已被注入
        assert MessageStreamService._backend is backend
        # reset 会清除，不影响后续测试

    def test_kafka_path_injects_backend(self):
        try:
            from knowledge_common.message_stream.backends.kafka_stream import KafkaStreamBackend  # noqa: F401
        except ImportError:
            pytest.skip('aiokafka 未安装,跳过 init_from_settings Kafka 路径测试')

        settings = SimpleNamespace(
            message_stream_backend='kafka',
            message_stream_kafka_bootstrap_servers='b:9092',
            message_stream_kafka_client_id='ut',
            message_stream_kafka_security_protocol='PLAINTEXT',
            message_stream_kafka_sasl_mechanism='',
            message_stream_kafka_sasl_username='',
            message_stream_kafka_sasl_password='',
            message_stream_kafka_acks='all',
            message_stream_kafka_linger_ms=5,
            message_stream_kafka_request_timeout_ms=30000,
            message_stream_kafka_session_timeout_ms=10000,
            message_stream_kafka_heartbeat_interval_ms=3000,
            message_stream_kafka_auto_offset_reset='earliest',
            message_stream_kafka_create_topic_partitions=1,
            message_stream_kafka_create_topic_replication_factor=1,
        )
        backend = MessageStreamService.init_from_settings(settings)
        assert isinstance(backend, KafkaStreamBackend)
        assert MessageStreamService._backend is backend

    def test_redis_path_without_redis_propagates_error(self):
        settings = SimpleNamespace(
            message_stream_backend='redis',
            message_stream_redis_maxlen=100000,
        )
        with pytest.raises(MessageStreamError):
            MessageStreamService.init_from_settings(settings, redis=None)
        # 错误路径下 _backend 不应被设置
        assert MessageStreamService._backend is None


# =============================================================================
# 7.9 KafkaStreamBackend 字段编解码(不连真 Kafka,验证实现)
# =============================================================================


try:
    from knowledge_common.message_stream.backends.kafka_stream import (  # noqa: E402
        KafkaStreamBackend,
        _decode_headers,
        _decode_value,
        _encode_headers,
        _encode_value,
    )
    _KAFKA_AVAILABLE = True
except ImportError:
    _KAFKA_AVAILABLE = False


@pytest.mark.skipif(not _KAFKA_AVAILABLE, reason='aiokafka 未安装')
class TestKafkaBackendFieldCodec:
    """Kafka 消息字段编解码:跟 Redis 后端保持一致的语义"""

    def test_encode_decode_value_dict(self):
        raw = _encode_value({'k': 'v', 'n': 1})
        assert isinstance(raw, bytes)
        assert _decode_value(raw) == {'k': 'v', 'n': 1}

    def test_encode_decode_value_str(self):
        assert _decode_value(_encode_value('plain')) == 'plain'

    def test_encode_value_already_bytes(self):
        raw = b'bytes-data'
        assert _encode_value(raw) is raw

    def test_decode_value_none(self):
        assert _decode_value(None) is None

    def test_encode_decode_headers_str(self):
        raw = _encode_headers({'trace_id': 'abc'})
        assert _decode_headers(raw) == {'trace_id': 'abc'}

    def test_encode_decode_headers_dict(self):
        raw = _encode_headers({'meta': {'k': 'v'}})
        assert _decode_headers(raw) == {'meta': {'k': 'v'}}

    def test_decode_headers_empty(self):
        assert _decode_headers(None) == {}
        assert _decode_headers([]) == {}

    def test_backend_constructor_stores_params(self):
        """不连真 Kafka,仅验证 __init__ 参数透传与懒加载属性初始化"""
        backend = KafkaStreamBackend(
            bootstrap_servers='broker:9092',
            client_id='ut',
            security_protocol='PLAINTEXT',
            acks='1',
            linger_ms=20,
            create_topic_partitions=5,
            create_topic_replication_factor=2,
        )
        assert backend._bootstrap_servers == 'broker:9092'
        assert backend._client_id == 'ut'
        assert backend._acks == '1'
        assert backend._linger_ms == 20
        assert backend._create_topic_partitions == 5
        assert backend._create_topic_replication_factor == 2
        # 懒加载状态
        assert backend._producer is None
        assert backend._admin is None
        assert backend._consumers == {}


@pytest.mark.skipif(not _KAFKA_AVAILABLE, reason='aiokafka 未安装')
class TestKafkaBackendShutdown:
    """KafkaStreamBackend.shutdown: 不连真服务也能幂等 close"""

    @pytest.mark.asyncio
    async def test_shutdown_with_no_clients_is_noop(self):
        backend = KafkaStreamBackend(bootstrap_servers='unused:9092')
        # 没启过任何客户端,shutdown 不应抛
        await backend.shutdown()
        assert backend._producer is None
        assert backend._admin is None
        assert backend._consumers == {}

    @pytest.mark.asyncio
    async def test_shutdown_calls_close_on_consumer(self):
        backend = KafkaStreamBackend(bootstrap_servers='unused:9092')
        # 手工塞一个 mock consumer
        mock_consumer = AsyncMock()
        mock_consumer.close = AsyncMock()
        backend._consumers['t::g::c'] = mock_consumer
        await backend.shutdown()
        mock_consumer.close.assert_awaited_once()
        assert backend._consumers == {}


# =============================================================================
# 6.1 admin lifespan 接入范式静态验证
# =============================================================================


class Test61AdminLifespanIntegration:
    """验证 admin server.py 已按规范接入 MessageStreamService"""

    def test_admin_server_imports_message_stream(self):
        """admin/server.py 必须 import MessageStreamService + MessageStreamConfig"""
        server_py = (
            _PROJECT_ROOT
            / 'knowledge-admin' / 'src' / 'knowledge_admin' / 'server' / 'server.py'
        )
        text = server_py.read_text(encoding='utf-8')
        assert 'from knowledge_common.message_stream import MessageStreamService' in text
        assert 'MessageStreamConfig' in text

    def test_admin_lifespan_calls_init_register_start(self):
        server_py = (
            _PROJECT_ROOT
            / 'knowledge-admin' / 'src' / 'knowledge_admin' / 'server' / 'server.py'
        )
        text = server_py.read_text(encoding='utf-8')
        # 三步范式(init_from_settings 代理 init + 工厂)
        assert 'MessageStreamService.init_from_settings(' in text
        assert 'MessageStreamService.register_consumer_paths(' in text
        assert 'MessageStreamService.discover_and_start()' in text
        # shutdown
        assert 'MessageStreamService.shutdown()' in text

    def test_rag_server_uses_same_pattern(self):
        """rag server.py 也按同一范式接入"""
        server_py = (
            _PROJECT_ROOT
            / 'knowledge-content' / 'src' / 'knowledge_content' / 'server' / 'server.py'
        )
        text = server_py.read_text(encoding='utf-8')
        assert 'from knowledge_common.message_stream import MessageStreamService' in text
        assert 'MessageStreamConfig' in text
        assert 'MessageStreamService.init_from_settings(' in text
        assert 'MessageStreamService.register_consumer_paths(' in text
        assert 'MessageStreamService.discover_and_start()' in text
        assert 'MessageStreamService.shutdown()' in text

    def test_env_config_drives_backend_selection(self):
        """admin .env 必须含 MESSAGE_STREAM_BACKEND 字段(.env 切换机制证据)"""
        env_file = (
            _PROJECT_ROOT
            / 'knowledge-admin' / 'src' / 'configs' / '.env.dev'
        )
        text = env_file.read_text(encoding='utf-8')
        assert 'MESSAGE_STREAM_BACKEND' in text
        # 至少含 Redis 默认 + Kafka bootstrap 字段
        assert "MESSAGE_STREAM_BACKEND = 'redis'" in text
        assert 'MESSAGE_STREAM_KAFKA_BOOTSTRAP_SERVERS' in text
