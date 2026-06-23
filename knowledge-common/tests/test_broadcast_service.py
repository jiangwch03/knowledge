"""
消息广播服务单元 / 集成测试套件

覆盖 openspec/changes/broadcast-service-abstraction/tasks.md 中:
- 7.1 @subscriber 装饰器注册、去重、BroadcastMessage 解析
- 7.2 BroadcastService 生命周期（init → discover → shutdown）
- 7.3 端到端集成测试（publish → subscriber handler 收到消息）

分层:
- ✅ 静态/Mock 层: 不依赖 Redis，可任意环境跑通
- ⚠️ 真 Redis 集成层: 6379 端口未连通时自动 skip

运行:
    cd /Users/jsir/programfiles/qoder/knowledge
    .venv/bin/pytest knowledge-common/tests/test_broadcast_service.py -v -s
"""
from __future__ import annotations

import asyncio
import socket
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 让测试可导入 knowledge-common
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 加载 admin .env（端到端测试拿真实 Redis 凭证用）
from dotenv import load_dotenv  # noqa: E402

_ENV_FILE = _PROJECT_ROOT / 'knowledge-admin' / 'src' / 'configs' / '.env.dev'
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)

from knowledge_common.broadcast import (  # noqa: E402
    BroadcastError,
    BroadcastMessage,
    BroadcastService,
    subscriber,
)
from knowledge_common.broadcast.backends.base import BroadcastBackend  # noqa: E402
from knowledge_common.broadcast.backends.redis_pubsub import RedisPubSubBackend  # noqa: E402


# =============================================================================
# Fixtures
# =============================================================================


def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    """检查端口是否可连接（用于判断 Redis 是否可用）"""
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
    """每个测试前后都 reset，保证订阅者表 / 路径 / backend 清零"""
    BroadcastService.reset()
    yield
    BroadcastService.reset()


# =============================================================================
# 7.1 @subscriber 装饰器 + BroadcastMessage
# =============================================================================


class Test71SubscriberDecorator:
    """@subscriber 装饰器: 基本注册、参数透传、去重"""

    def test_basic_registration(self):
        @subscriber(channel='test:ch1')
        async def handler(msg):
            pass

        key = f'{handler.__module__}.handler'
        assert key in BroadcastService._subscribers
        info = BroadcastService._subscribers[key]
        assert info.channel == 'test:ch1'
        assert info.handler is handler

    def test_custom_id_overrides_default(self):
        @subscriber(channel='test:ch', id='my-custom-id')
        async def h(msg):
            pass

        assert 'my-custom-id' in BroadcastService._subscribers
        info = BroadcastService._subscribers['my-custom-id']
        assert info.channel == 'test:ch'
        assert info.handler is h

    def test_duplicate_registration_skipped(self):
        @subscriber(channel='test:ch', id='dup')
        async def h1(msg):
            pass

        before = len(BroadcastService._subscribers)

        @subscriber(channel='test:ch', id='dup')
        async def h2(msg):
            pass

        after = len(BroadcastService._subscribers)
        assert before == after
        # 原 handler 仍然是 h1，不被 h2 覆盖
        assert BroadcastService._subscribers['dup'].handler is h1

    def test_decorator_returns_original_function(self):
        async def orig(msg):
            return 'x'

        decorated = subscriber(channel='test:ch')(orig)
        assert decorated is orig

    def test_multiple_channels_register_independently(self):
        @subscriber(channel='ch:a', id='sub-a')
        async def ha(msg):
            pass

        @subscriber(channel='ch:b', id='sub-b')
        async def hb(msg):
            pass

        assert BroadcastService._subscribers['sub-a'].channel == 'ch:a'
        assert BroadcastService._subscribers['sub-b'].channel == 'ch:b'


class Test71BroadcastMessage:
    """BroadcastMessage 数据类: 字段访问、repr"""

    def test_field_access(self):
        msg = BroadcastMessage(channel='test:ch', payload={'k': 'v'}, timestamp=1234.5)
        assert msg.channel == 'test:ch'
        assert msg.payload == {'k': 'v'}
        assert msg.timestamp == 1234.5

    def test_frozen(self):
        msg = BroadcastMessage(channel='ch', payload='x', timestamp=0)
        with pytest.raises(Exception):
            msg.channel = 'other'  # type: ignore[misc]

    def test_repr_contains_channel(self):
        msg = BroadcastMessage(channel='test:ch', payload='data', timestamp=0)
        s = repr(msg)
        assert 'test:ch' in s
        assert 'data' in s


class Test71BroadcastError:
    """BroadcastError 异常"""

    def test_basic_message(self):
        e = BroadcastError('boom')
        assert str(e) == 'boom'
        assert e.channel is None
        assert e.cause is None

    def test_with_channel(self):
        e = BroadcastError('fail', channel='test:ch')
        assert e.channel == 'test:ch'

    def test_with_cause(self):
        cause = ValueError('inner')
        e = BroadcastError('outer', cause=cause)
        assert e.cause is cause

    def test_is_exception_subclass(self):
        assert issubclass(BroadcastError, Exception)


# =============================================================================
# 7.2 BroadcastService 生命周期
# =============================================================================


class _StubBackend(BroadcastBackend):
    """测试用最小后端: 可控行为"""

    def __init__(self):
        self.start_called = False
        self.publish_calls: list[tuple[str, str | bytes]] = []
        self.shutdown_called = False
        self._dispatch_fn = None
        self._channels: list[str] = []

    async def start_listening(self, channels, dispatch_fn):
        self.start_called = True
        self._channels = channels
        self._dispatch_fn = dispatch_fn

    async def add_channel(self, channel):
        self._channels.append(channel)

    async def remove_channel(self, channel):
        if channel in self._channels:
            self._channels.remove(channel)

    async def publish(self, channel, message):
        self.publish_calls.append((channel, message))
        return 1

    async def shutdown(self):
        self.shutdown_called = True


class Test72Lifecycle:
    """BroadcastService 生命周期: init → discover → shutdown"""

    @pytest.mark.asyncio
    async def test_discover_without_init_raises(self):
        with pytest.raises(BroadcastError):
            await BroadcastService.discover_and_start()

    @pytest.mark.asyncio
    async def test_publish_without_init_raises(self):
        with pytest.raises(BroadcastError):
            await BroadcastService.publish('ch', 'msg')

    @pytest.mark.asyncio
    async def test_init_creates_backend(self):
        mock_redis = MagicMock()
        BroadcastService.init(redis=mock_redis)
        assert BroadcastService._backend is not None
        assert isinstance(BroadcastService._backend, RedisPubSubBackend)

    @pytest.mark.asyncio
    async def test_register_paths_deduplicates(self):
        BroadcastService.register_subscriber_paths(['a.b', 'a.b', 'c.d'])
        BroadcastService.register_subscriber_paths(['c.d', 'e.f'])
        assert BroadcastService._scan_paths == ['a.b', 'c.d', 'e.f']

    @pytest.mark.asyncio
    async def test_discover_starts_backend(self):
        stub = _StubBackend()
        BroadcastService._backend = stub

        # 手动注册一个 subscriber
        @subscriber(channel='test:discover', id='ut-discover')
        async def handler(msg):
            pass

        BroadcastService.register_subscriber_paths(['fake.path'])
        with patch.object(BroadcastService, '_import_subtree'):
            await BroadcastService.discover_and_start()

        assert stub.start_called
        assert 'test:discover' in stub._channels
        assert BroadcastService._started

    @pytest.mark.asyncio
    async def test_shutdown_calls_backend_shutdown(self):
        stub = _StubBackend()
        BroadcastService._backend = stub
        BroadcastService._started = True

        await BroadcastService.shutdown()

        assert stub.shutdown_called
        assert not BroadcastService._started

    @pytest.mark.asyncio
    async def test_reset_clears_all_state(self):
        stub = _StubBackend()
        BroadcastService._backend = stub
        BroadcastService._started = True
        BroadcastService._scan_paths = ['x']
        BroadcastService._subscribers = {'x': MagicMock()}

        BroadcastService.reset()

        assert BroadcastService._backend is None
        assert BroadcastService._subscribers == {}
        assert BroadcastService._scan_paths == []
        assert not BroadcastService._started

    @pytest.mark.asyncio
    async def test_no_scan_paths_warns_but_no_raise(self):
        stub = _StubBackend()
        BroadcastService._backend = stub
        # 不注册路径
        await BroadcastService.discover_and_start()
        # 没有启动后端
        assert not stub.start_called

    @pytest.mark.asyncio
    async def test_publish_encodes_dict_as_json(self):
        stub = _StubBackend()
        BroadcastService._backend = stub

        await BroadcastService.publish('ch', {'key': 'value'})

        assert len(stub.publish_calls) == 1
        ch, msg = stub.publish_calls[0]
        assert ch == 'ch'
        assert '"key"' in msg
        assert '"value"' in msg

    @pytest.mark.asyncio
    async def test_publish_string_passed_as_is(self):
        stub = _StubBackend()
        BroadcastService._backend = stub

        await BroadcastService.publish('ch', 'plain-text')

        ch, msg = stub.publish_calls[0]
        assert msg == 'plain-text'


# =============================================================================
# 7.3 端到端集成测试（真 Redis，不可用时 skip）
# =============================================================================


class Test73EndToEndRealRedis:
    """真 Redis 端到端: publish → subscriber handler 收到消息"""

    @pytest.mark.asyncio
    async def test_end_to_end_broadcast(self, redis_running):
        if not redis_running:
            pytest.skip('Redis 6379 未连通，跳过端到端集成测试')

        from redis import asyncio as aioredis

        from knowledge_common.config.env import RedisConfig

        unique = uuid.uuid4().hex[:8]
        channel = f'broadcast-ut:e2e:{unique}'

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
            pytest.skip(f'Redis 鉴权 / 连接失败，跳过端到端集成测试: {e!r}')

        try:
            received: list[BroadcastMessage] = []
            done = asyncio.Event()

            # 注册 subscriber
            @subscriber(channel=channel, id=f'ut-e2e-{unique}')
            async def handler(msg: BroadcastMessage) -> None:
                received.append(msg)
                done.set()

            # 初始化 + 启动
            BroadcastService.init(redis=redis_client)
            # 手动注入 subscriber（已经通过装饰器注册了）
            with patch.object(BroadcastService, '_import_subtree'):
                BroadcastService.register_subscriber_paths(['fake'])
                await BroadcastService.discover_and_start()

            # 等一小段时间让 listen loop 建立
            await asyncio.sleep(0.3)

            # 发布消息
            n = await BroadcastService.publish(channel, {'action': 'test', 'id': unique})
            assert isinstance(n, int)

            # 等待消费（最多 5 秒）
            try:
                await asyncio.wait_for(done.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.fail(f'未收到广播消息: channel={channel}')

            assert len(received) >= 1
            msg = received[0]
            assert msg.channel == channel
            assert msg.payload == {'action': 'test', 'id': unique}
            assert msg.timestamp > 0

        finally:
            await BroadcastService.shutdown()
            await redis_client.aclose()


# =============================================================================
# 附加: 静态验证 admin/rag server.py 已按规范接入 BroadcastService
# =============================================================================


class TestLifespanStaticVerification:
    """验证 server.py 已按规范接入 BroadcastService"""

    def test_admin_server_imports_broadcast(self):
        server_py = (
            _PROJECT_ROOT
            / 'knowledge-admin' / 'src' / 'knowledge_admin' / 'server' / 'server.py'
        )
        text = server_py.read_text(encoding='utf-8')
        assert 'from knowledge_common.broadcast import BroadcastService' in text
        assert 'BroadcastService.init(' in text
        assert 'BroadcastService.register_subscriber_paths(' in text
        assert 'BroadcastService.discover_and_start()' in text
        assert 'BroadcastService.shutdown()' in text

    def test_rag_server_imports_broadcast(self):
        server_py = (
            _PROJECT_ROOT
            / 'knowledge-rag' / 'src' / 'knowledge_rag' / 'server' / 'server.py'
        )
        text = server_py.read_text(encoding='utf-8')
        assert 'from knowledge_common.broadcast import BroadcastService' in text
        assert 'BroadcastService.init(' in text
        assert 'BroadcastService.register_subscriber_paths(' in text
        assert 'BroadcastService.discover_and_start()' in text
        assert 'BroadcastService.shutdown()' in text

    def test_admin_registers_admin_subscribers(self):
        """knowledge_common.message.subscriber 是 BroadcastService 内置默认路径，无需显式注册"""
        server_py = (
            _PROJECT_ROOT
            / 'knowledge-admin' / 'src' / 'knowledge_admin' / 'server' / 'server.py'
        )
        text = server_py.read_text(encoding='utf-8')
        assert 'knowledge_admin.message.subscriber' in text

    def test_rag_registers_rag_subscribers(self):
        """knowledge_common.message.subscriber 是 BroadcastService 内置默认路径，无需显式注册"""
        server_py = (
            _PROJECT_ROOT
            / 'knowledge-rag' / 'src' / 'knowledge_rag' / 'server' / 'server.py'
        )
        text = server_py.read_text(encoding='utf-8')
        assert 'knowledge_rag.message.subscriber' in text
