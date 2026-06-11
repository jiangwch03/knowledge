"""
Redis Key 统一定义

集中管理所有 Redis 键名定义，替代分散在各处的硬编码 key 字符串。

命名规范：
    - 前缀用冒号分隔：模块:业务:标识
    - 动态 key 通过 format_key() 或 f-string 拼接
    - 锁 key 统一 lock: 前缀

典型用法：
    from knowledge_common.redis import RedisKey, LockKey

    # 数据 key
    key = RedisKey.sys_dict_key('user_gender')       # → 'sys_dict:user_gender'
    key = RedisKey.access_token_key('session_abc')    # → 'access_token:session_abc'

    # 锁 key
    key = LockKey.app_startup_key('knowledge-admin')  # → 'lock:app:startup:knowledge-admin'
"""

from knowledge_common.config.env import AppConfig


class RedisKey:
    """
    Redis 数据键名定义

    每个类属性为 key 前缀（不含动态部分），通过 @staticmethod 方法生成完整 key。
    """

    # ==================== 前缀常量 ====================

    ACCESS_TOKEN = 'access_token'
    SYS_DICT = 'sys_dict'
    SYS_CONFIG = 'sys_config'
    API_CACHE = 'api_cache'
    API_RATE_LIMIT = 'api_rate_limit'
    CAPTCHA_CODES = 'captcha_codes'
    ACCOUNT_LOCK = 'account_lock'
    PASSWORD_ERROR_COUNT = 'password_error_count'
    SMS_CODE = 'sms_code'

    # ==================== 缓存名称 → 展示名映射 ====================

    CACHE_KEY_REMARKS: dict[str, str] = {
        ACCESS_TOKEN: '登录令牌信息',
        SYS_DICT: '数据字典',
        SYS_CONFIG: '配置信息',
        API_CACHE: '接口响应缓存',
        API_RATE_LIMIT: '接口限流',
        CAPTCHA_CODES: '图片验证码',
        ACCOUNT_LOCK: '用户锁定',
        PASSWORD_ERROR_COUNT: '密码错误次数',
        SMS_CODE: '短信验证码',
    }

    # ==================== Key 生成方法 ====================

    @staticmethod
    def access_token_key(session_id: str) -> str:
        """登录令牌 key"""
        return f'{RedisKey.ACCESS_TOKEN}:{session_id}'

    @staticmethod
    def sys_dict_key(dict_type: str) -> str:
        """数据字典 key"""
        return f'{RedisKey.SYS_DICT}:{dict_type}'

    @staticmethod
    def sys_config_key(config_key: str) -> str:
        """参数配置 key"""
        return f'{RedisKey.SYS_CONFIG}:{config_key}'

    @staticmethod
    def api_cache_key(namespace: str, cache_key: str) -> str:
        """接口缓存 key"""
        return f'{RedisKey.API_CACHE}:{namespace}:{cache_key}'

    @staticmethod
    def api_rate_limit_key(namespace: str) -> str:
        """接口限流 key"""
        return f'{RedisKey.API_RATE_LIMIT}:{namespace}'

    @staticmethod
    def captcha_key(uuid: str) -> str:
        """图片验证码 key"""
        return f'{RedisKey.CAPTCHA_CODES}:{uuid}'

    @staticmethod
    def account_lock_key(username: str) -> str:
        """用户锁定 key"""
        return f'{RedisKey.ACCOUNT_LOCK}:{username}'

    @staticmethod
    def password_error_count_key(username: str) -> str:
        """密码错误次数 key"""
        return f'{RedisKey.PASSWORD_ERROR_COUNT}:{username}'

    @staticmethod
    def sms_code_key(phone: str) -> str:
        """短信验证码 key"""
        return f'{RedisKey.SMS_CODE}:{phone}'


class LockKey:
    """
    Redis 分布式锁键名定义

    所有锁 key 统一 lock: 前缀，避免与数据 key 冲突。
    """

    PREFIX = 'lock'

    # ==================== Key 生成方法 ====================

    @staticmethod
    def app_startup_key(app_name: str | None = None) -> str:
        """
        应用启动锁 key

        :param app_name: 应用名称，默认使用当前 AppConfig.app_name
        """
        name = app_name or AppConfig.app_name
        return f'{LockKey.PREFIX}:app:startup:{name}'

    @staticmethod
    def custom_key(name: str) -> str:
        """
        自定义锁 key（通用场景）

        :param name: 锁名称（如 'sync:job:xxx'）
        """
        return f'{LockKey.PREFIX}:{name}'
