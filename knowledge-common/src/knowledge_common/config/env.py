import argparse
import configparser
import json
import os
import sys
from typing import Annotated, Literal

from dotenv import load_dotenv
from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings
from pydantic_settings.sources import NoDecode
from knowledge_common.utils.project_path_util import infer_current_project, resolve_workspace_root


class AppSettings(BaseSettings):
    """
    应用配置
    """

    app_env: str = 'dev'
    app_name: str = 'knowledge'
    app_root_path: str = '/api/common'
    app_host: str = '0.0.0.0'
    app_port: int = 9099
    app_version: str = '0.0.1'
    app_reload: bool = True
    app_workers: int = 1
    app_ip_location_query: bool = True
    app_same_time_login: bool = True
    app_demo_mode: bool = False
    app_disable_swagger: bool = False
    app_disable_redoc: bool = False
    app_trusted_proxy_ips: str = '127.0.0.1,::1'
    app_trusted_proxy_hops: int = 1

class JwtSettings(BaseSettings):
    """
    Jwt配置
    """

    jwt_secret_key: str = 'b01c66dc2c58dc6a0aabfe2144256be36226de378bf87f72c0c795dda67f4d55'
    jwt_algorithm: str = 'HS256'
    jwt_expire_minutes: int = 1440
    jwt_redis_expire_minutes: int = 30

class DataBaseSettings(BaseSettings):
    """
    数据库配置
    """

    db_type: Literal['mysql', 'postgresql'] = 'mysql'
    db_host: str = '127.0.0.1'
    db_port: int = 3306
    db_username: str = 'root'
    db_password: str = ''
    db_database: str = 'knowledge'
    db_echo: bool = True
    db_max_overflow: int = 10
    db_pool_size: int = 50
    db_pool_recycle: int = 3600
    db_pool_timeout: int = 30

    @computed_field
    @property
    def sqlglot_parse_dialect(self) -> str:
        if self.db_type == 'postgresql':
            return 'postgres'
        return self.db_type


class RedisSettings(BaseSettings):
    """
    Redis配置
    """

    redis_host: str = '127.0.0.1'
    redis_port: int = 6379
    redis_username: str = ''
    redis_password: str = ''
    redis_database: int = 0
    # LangGraph 短期记忆独立 Redis 库，默认与业务库隔离
    redis_saver_database: int = 1


class LogSettings(BaseSettings):
    """
    日志与队列配置
    """

    log_mask_enabled: bool = True
    log_mask_placeholder: str = '******'
    log_mask_fields: str = (
        'password,old_password,new_password,confirm_password,api_key,token,access_token,refresh_token,'
        'authorization,client_secret,secret,secret_key,private_key,private_key_pem,credential,credentials,'
        'sms_code,captcha_code,system_prompt'
    )
    log_partial_mask_fields: str = 'phonenumber,phone,mobile,email'
    log_config_secret_patterns: str = 'password,token,secret,key,private,credential,access,jwt,captcha,sms'
    log_stream_dedup_ttl: int = 3600
    log_stream_dedup_prefix: str = 'log:dedup'

    @staticmethod
    def get_dedup_prefix(app_name: str) -> str:
        """
        根据 app_name 派生去重 key 前缀

        避免 admin 端和 rag 端 event_id 冲突（虽然 UUID 撞概率极低，但语义上更清晰）。
        """
        return f'{LogConfig.log_stream_dedup_prefix}:{app_name}'

    loguru_json: bool = False
    loguru_level: str = 'INFO'
    loguru_stdout: bool = True
    log_file_enabled: bool = True
    log_file_base_dir: str = 'logs'
    loguru_rotation: str = '50MB'
    loguru_retention: str = '30 days'
    loguru_compression: str = 'zip'
    log_instance_id: str = 'prod'
    log_service_name: str = 'ruoyi-fastapi-backend'
    log_worker_id: str = 'auto'


class TransportCryptoSettings(BaseSettings):
    """
    传输层加解密配置
    """

    transport_crypto_enabled: bool = True
    transport_crypto_mode: Literal['off', 'optional', 'required'] = 'optional'
    transport_crypto_algorithm: str = 'RSA_OAEP_AES_256_GCM'
    transport_crypto_kid: str = 'default'
    transport_crypto_public_key: str = ''
    transport_crypto_private_key: str = ''
    transport_crypto_legacy_key_pairs: str = '[]'
    transport_crypto_rsa_key_size: int = 2048
    transport_crypto_public_key_ttl_seconds: int = 3600
    transport_crypto_frontend_config_ttl_seconds: int = 300
    transport_crypto_max_get_url_length: int = 4096
    transport_crypto_clock_skew_seconds: int = 120
    transport_crypto_replay_ttl_seconds: int = 300
    transport_crypto_enabled_paths: str = ''
    transport_crypto_required_paths: str = ''
    transport_crypto_exclude_paths: str = (
        '/openapi.json,/docs,/docs/oauth2-redirect,/redoc,'
        '/transport/crypto/frontend-config,/transport/crypto/public-key,/common/download,/common/download/resource'
    )


class MessageStreamSettings(BaseSettings):
    """
    消息流后端选择与跨后端公共参数

    - 修改 .env 中的 ``MESSAGE_STREAM_BACKEND`` 即可在 redis / kafka 后端间切换
    - 切换时业务侧代码、装饰器、消息字段、异常类型均保持不变
    """

    # ---------- 后端选择 ----------
    message_stream_backend: Literal['redis', 'kafka'] = 'redis'

    # ---------- 跨后端公共消费参数 ----------
    message_stream_consume_block_ms: int = 2000
    message_stream_consume_batch_size: int = 100
    message_stream_claim_idle_ms: int = 60000
    message_stream_claim_interval_ms: int = 5000

    # ---------- Redis 后端专属 ----------
    message_stream_redis_maxlen: int = 100000

    # ---------- Kafka 后端专属 ----------
    message_stream_kafka_bootstrap_servers: str = 'localhost:9092'
    message_stream_kafka_client_id: str = 'knowledge'
    message_stream_kafka_security_protocol: str = 'PLAINTEXT'  # PLAINTEXT / SSL / SASL_PLAINTEXT / SASL_SSL
    message_stream_kafka_sasl_mechanism: str = ''               # PLAIN / SCRAM-SHA-256 / SCRAM-SHA-512
    message_stream_kafka_sasl_username: str = ''
    message_stream_kafka_sasl_password: str = ''
    message_stream_kafka_acks: str = 'all'                      # 0 / 1 / all
    message_stream_kafka_linger_ms: int = 5
    message_stream_kafka_request_timeout_ms: int = 30000
    message_stream_kafka_session_timeout_ms: int = 10000
    message_stream_kafka_heartbeat_interval_ms: int = 3000
    message_stream_kafka_auto_offset_reset: str = 'earliest'    # earliest / latest
    message_stream_kafka_create_topic_partitions: int = 1
    message_stream_kafka_create_topic_replication_factor: int = 1

    @property
    def is_kafka(self) -> bool:
        return self.message_stream_backend == 'kafka'

    @property
    def is_redis(self) -> bool:
        return self.message_stream_backend == 'redis'

class StreamTopicSettings(BaseSettings):
    """
    消息流主题配置
    """
    # 消费组ID
    group_id: str = 'knowledge_content'
    # 文档解析待处理队列
    document_parse_pending: str = 'document.parse.pending'
    # 文档 Markdown 合并待处理队列
    document_md_pending: str = 'document.md.pending'
    # 爬取任务执行队列
    crawl_task_pending: str = 'crawl.task.pending'
    # 爬取文档持久化（合并 Markdown 并落库）
    crawl_document_pending: str = 'crawl.document.pending'

class UploadSettings(BaseSettings):
    """
    上传配置
    """

    UPLOAD_PREFIX: str = '/profile'
    UPLOAD_PATH: str = 'vf_admin/upload_path'
    UPLOAD_TEMP_PATH: str = 'vf_admin/upload_path/tmp'
    UPLOAD_MACHINE: str = 'A'
    DEFAULT_ALLOWED_EXTENSION: Annotated[list[str], NoDecode] = Field(default = list)
    UPLOAD_MAX_SIZE: int = 100 * 1024 * 1024
    DOWNLOAD_PATH: str = 'vf_admin/download_path'

    @field_validator('DEFAULT_ALLOWED_EXTENSION', mode='before')
    @classmethod
    def _parse_extensions(cls, v: str | list[str]) -> list[str]:
        """
        从 .env 文件读取时支持两种格式：
        - 逗号分隔：DEFAULT_ALLOWED_EXTENSION = bmp,gif,jpg
        - JSON 数组：DEFAULT_ALLOWED_EXTENSION = '["bmp","gif","jpg"]'
        """
        if isinstance(v, list):
            return v
        v_stripped = v.strip().strip("'\"")
        if v_stripped.startswith('[') and v_stripped.endswith(']'):
            try:
                return json.loads(v_stripped)
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in v_stripped.split(',') if item.strip()]

    def model_post_init(self, __context) -> None:
        if not os.path.exists(self.UPLOAD_PATH):
            os.makedirs(self.UPLOAD_PATH)
        if not os.path.exists(self.UPLOAD_TEMP_PATH):
            os.makedirs(self.UPLOAD_TEMP_PATH)
        if not os.path.exists(self.DOWNLOAD_PATH):
            os.makedirs(self.DOWNLOAD_PATH)


class CachePathConfig:
    """
    缓存目录配置
    """

    PATH = os.path.join(os.path.abspath(os.getcwd()), 'caches')
    PATHSTR = 'caches'

class MinerUSettings(BaseSettings):
    """
    MineU 解析服务配置
    """

    mineru_url: str = ''
    mineru_file_urls_uri: str = '/api/v4/file-urls/batch'
    mineru_extract_results_uri: str = '/api/v4/extract-results/batch'
    mineru_token: str = ''
    mineru_model_version: str = 'pipeline'
    mineru_html_model_version: str = 'MinerU-HTML'
    mineru_callback_url: str = ''
    mineru_seed: str = ''


class Crawl4aiSettings(BaseSettings):
    """
    crawl4ai 爬取引擎配置

    支持两种调用模式（通过 crawl4ai_mode 切换）：
    - sdk: 本地 SDK 模式，进程内直接调用 crawl4ai Python 库（默认）
    - service: 远程服务模式，通过 HTTP 调用独立部署的 crawl4ai Docker 服务

    所有字段均可通过 .env 环境变量覆盖。
    """

    # ---------- 模式切换 ----------

    # 调用模式：sdk（本地SDK）或 service（远程服务）
    crawl4ai_mode: str = 'sdk'
    # 远程服务地址（service 模式必填）
    crawl4ai_service_url: str = 'http://localhost:11235'
    # 远程服务认证 Token（对应 Docker 部署的 CRAWL4AI_API_TOKEN，0.9.0+ 默认开启认证）
    crawl4ai_api_token: str = 'CRAWL4AI_API_TOKEN_123456'
    # HTTP 请求超时秒数（service 模式）
    crawl4ai_request_timeout: int = 300

    # ---------- BrowserConfig 相关（sdk 模式 + service 模式共用） ----------

    # 无头浏览器模式
    crawl4ai_headless: bool = True
    # 浏览器 User-Agent
    crawl4ai_user_agent: str = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
    # 视口宽度（标准桌面，避免移动端布局）
    crawl4ai_viewport_width: int = 1920
    # 视口高度
    crawl4ai_viewport_height: int = 1080
    # 基础反爬防御，无副作用，始终开启
    crawl4ai_enable_stealth: bool = True
    # 生产环境关闭 crawl4ai 内部日志，保持日志干净
    crawl4ai_verbose: bool = False

    # ---------- CrawlerRunConfig 相关 ----------

    # 始终排除的噪音标签，确保 Markdown 输出干净
    crawl4ai_excluded_tags: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ['nav', 'footer', 'header', 'aside', 'script', 'style', 'form', 'iframe']
    )
    # 保留结构化输出，不提取纯文本
    crawl4ai_only_text: bool = False
    # 过滤零碎内容块（少于此词数的块丢弃）
    crawl4ai_word_count_threshold: int = 10
    # 深度爬取时流式返回结果，边爬边处理
    crawl4ai_stream: bool = True


    # ---------- 任务超时控制 ----------

    # 爬取任务超时阈值（分钟）：RUNNING 且 started_time 超此值时触发超时兜底
    # - 执行锁仍被占用：仅写 Redis 取消标志，由活执行器自报 FAILED+TIMEOUT
    # - 执行锁可抢到：判定进程已死，由僵尸扫描直接 PENDING 续跑（不计 retry_count）
    crawl4ai_task_timeout_minutes: int = 60

    # 僵尸 RUNNING 检测宽限（分钟）：update_time 超过此值且 crawl_task 锁可抢到，视为进程中断并直接 PENDING 续跑（不计 retry_count）
    # 须大于 DistributedLock 默认 expire（30s）并留足看门狗停更后的余量；生产发版/OOM 后靠此快速收尸
    crawl4ai_zombie_detect_minutes: int = 2

    # ---------- 失败重试控制 ----------

    # 规则自动重试次数上限（任务创建时写入 max_retry_count；LLM 人工重试时 max_retry_count += 本值）
    # 超过任务自身 max_retry_count 后升级为用户人工决策
    crawl4ai_rule_retry_limit: int = 2

    @field_validator('crawl4ai_excluded_tags', mode='before')
    @classmethod
    def _parse_excluded_tags(cls, v: str | list[str]) -> list[str]:
        """
        从 .env 文件读取时支持两种格式：
        - 逗号分隔：crawl4ai_excluded_tags = nav,footer,header
        - JSON 数组：crawl4ai_excluded_tags = '["nav","footer","header"]'
        """
        if isinstance(v, list):
            return v
        v_stripped = v.strip().strip("'\"")
        if v_stripped.startswith('[') and v_stripped.endswith(']'):
            try:
                return json.loads(v_stripped)
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in v_stripped.split(',') if item.strip()]


class AiModelFunctionAdapterSettings(BaseSettings):
    """
    模型功能适配配置

    用于配置各业务功能的模型适配参数，如功能点 param_id 等。
    所有字段均可通过 .env 环境变量覆盖。
    """

    # 爬取Agent功能适配参数ID
    crawler_agent_param_id: str = 'web_crawler_agent'
    # Markdown图片描述生成功能适配参数ID
    md_image_description_param_id: str = 'md_image_description'
    # TXT转Markdown功能适配参数ID
    txt_to_markdown_param_id: str = 'txt_to_markdown'


class SemaphoreSettings(BaseSettings):
    """
    分布式信号量配置

    各业务场景的令牌池大小，通过 .env 环境变量覆盖（如 SEMAPHORE_CRAWL_PIPELINE_SIZE=20）。
    """

    # 爬取流水线令牌池大小（DistributedSemaphore.create_pool size）
    # 对应 SemaphoreKey.crawl_pipeline_key()
    semaphore_crawl_pipeline_size: int = 10


class CrawlerAgentSettings(BaseSettings):
    """
    网页爬取 Agent 配置

    网页爬取 Agent 的业务运行参数，通过 .env 环境变量覆盖（如 CRAWLER_AGENT_MAX_REACT_ROUNDS=10）。
    """

    # ReAct 分析阶段最大轮次，达到上限后 LLM 停止工具调用
    crawler_agent_max_react_rounds: int = 50

    # 是否使用 deepagents create_deep_agent 作为 Supervisor（已固定为 deepagents，保留字段兼容旧 .env）
    crawler_agent_use_deepagents: bool = True

    # ── LangGraph interrupt 类型（Agent 图中断点标识）──

    # 用户提问节点：Agent 向用户发起业务提问
    interrupt_ask_user: str = 'ask_user'
    # 策略确认节点：用户确认/修改爬取策略配置
    interrupt_strategy_confirmation: str = 'strategy_confirmation'
    interrupt_rescope_confirmation: str = 'rescope_confirmation'


class MinioSettings(BaseSettings):
    """
    MinIO 配置
    """

    # MinIO 服务地址，指向宿主机已运行的 MinIO（端口 9000 为 S3 API 端口）
    minio_address: str = 'http://localhost:9000'
    # MinIO 访问密钥 ID（用户自定义账号）
    minio_access_key_id: str = 'jiangwch'
    # MinIO 秘密访问密钥（用户自定义密码）
    minio_secret_access_key: str = 'jiangwch'
    # MinIO 存储 bucket 名称（需预先在 MinIO 中创建）
    minio_bucket_name: str = 'minio-data'
    # Milvus 专用的存储 bucket 名称（需预先在 MinIO 中创建）
    milvus_bucket_name: str = 'milvus-data'
    # 知识库专用的存储 bucket 名称（需预先在 MinIO 中创建）
    knowledge_bucket_name: str = 'knowledge-data'
    # 是否使用 SSL/TLS 加密连接，false 表示使用明文 HTTP
    minio_use_ssl: bool = False
    # MinIO 对象路径前缀：原始文档
    minio_object_document_prefix: str = 'documents'
    # MinIO 对象路径前缀：文档中的图片
    minio_object_image_prefix: str = 'documents/images'
    # MinIO 对象路径前缀：合并后的 Markdown
    minio_object_markdown_prefix: str = 'documents/markdown'
    # MinIO 本地下载子目录（拼接在 UploadConfig.DOWNLOAD_PATH 后）
    minio_download_subdir: str = 'minio'


def _find_env_file(run_env: str) -> str | None:
    """
    按优先级在多个候选路径中查找 .env 文件
    优先级：cwd 向上回溯 src/configs/ -> 推断的当前项目 -> workspace 其他子项目
    """
    env_filename = f'.env.{run_env}' if run_env else '.env.dev'

    candidates = []

    # 1. 从 cwd 向上回溯，查找 src/configs/
    current = os.getcwd()
    prev = None
    while current != prev:
        candidates.append(os.path.join(current, 'src', 'configs', env_filename))
        prev = current
        current = os.path.dirname(current)

    # 2. workspace 下各子项目的 src/configs/，优先检查推断出的当前项目
    workspace_root = resolve_workspace_root()
    current_project = infer_current_project()
    if workspace_root:
        try:
            entries = sorted(os.listdir(workspace_root))
            # 优先把推断出的当前项目放前面
            if current_project and current_project in entries:
                entries.remove(current_project)
                entries.insert(0, current_project)
            for entry in entries:
                project_path = os.path.join(workspace_root, entry)
                if os.path.isdir(project_path) and entry.startswith('knowledge-'):
                    candidates.append(os.path.join(project_path, 'src', 'configs', env_filename))
        except Exception:
            pass

    seen: set[str] = set()
    for path in candidates:
        if path not in seen and os.path.isfile(path):
            return path
        seen.add(path)

    return None


class GetConfig:
    """
    获取配置
    """

    def __init__(self) -> None:
        self.parse_cli_args()

    def get_app_config(self) -> AppSettings:
        """
        获取应用配置
        """
        # 实例化应用配置模型
        return AppSettings()

    def get_jwt_config(self) -> JwtSettings:
        """
        获取Jwt配置
        """
        # 实例化Jwt配置模型
        return JwtSettings()

    def get_database_config(self) -> DataBaseSettings:
        """
        获取数据库配置
        """
        # 实例化数据库配置模型
        return DataBaseSettings()

    def get_redis_config(self) -> RedisSettings:
        """
        获取Redis配置
        """
        # 实例化Redis配置模型
        return RedisSettings()

    def get_log_config(self) -> LogSettings:
        """
        获取日志配置
        """
        return LogSettings()

    def get_transport_crypto_config(self) -> TransportCryptoSettings:
        """
        获取传输层加解密配置
        """
        return TransportCryptoSettings()


    def get_upload_config(self) -> UploadSettings:
        """
        获取上传配置
        """
        # 实例上传配置
        return UploadSettings()

    def get_mineru_config(self) -> MinerUSettings:
        """
        获取MineU配置
        """
        return MinerUSettings()

    def get_crawl4ai_config(self) -> Crawl4aiSettings:
        """
        获取 crawl4ai 爬取引擎配置
        """
        return Crawl4aiSettings()

    def get_ai_model_function_adapter_config(self) -> AiModelFunctionAdapterSettings:
        """
        获取模型功能适配配置
        """
        return AiModelFunctionAdapterSettings()

    def get_semaphore_config(self) -> SemaphoreSettings:
        """
        获取分布式信号量配置
        """
        return SemaphoreSettings()

    def get_crawler_agent_config(self) -> CrawlerAgentSettings:
        """
        获取网页爬取Agent配置
        """
        return CrawlerAgentSettings()

    def get_minio_config(self) -> MinioSettings:
        """
        获取MinIO配置
        """
        # 实例化MinIO配置模型
        return MinioSettings()

    def get_message_stream_config(self) -> MessageStreamSettings:
        """
        获取消息流后端配置
        """
        return MessageStreamSettings()


    def get_stream_topic_config(self) -> StreamTopicSettings:
        """
        Stream topic 配置
        """
        return StreamTopicSettings()

    @staticmethod
    def parse_cli_args() -> None:
        """
        解析命令行参数
        """
        # 检查是否在alembic环境中运行，如果是则跳过参数解析
        if 'alembic' in sys.argv[0] or any('alembic' in arg for arg in sys.argv):
            ini_config = configparser.ConfigParser()
            ini_config.read('alembic.ini', encoding='utf-8')
            if 'settings' in ini_config:
                # 获取env选项
                env_value = ini_config['settings'].get('env')
                os.environ['APP_ENV'] = env_value if env_value else 'dev'
        elif 'uvicorn' in sys.argv[0]:
            # 使用uvicorn启动时，命令行参数需要按照uvicorn的文档进行配置，无法自定义参数
            pass
        else:
            # 使用argparse定义命令行参数
            parser = argparse.ArgumentParser(description='命令行参数')
            parser.add_argument('--env', type=str, default='', help='运行环境')
            # 解析命令行参数
            args, _ = parser.parse_known_args()
            # 设置环境变量，如果未设置命令行参数，默认APP_ENV为dev
            os.environ['APP_ENV'] = args.env if args.env else 'dev'
        # 读取运行环境
        run_env = os.environ.get('APP_ENV', '')
        # 在多个候选路径中查找 .env 文件
        env_path = _find_env_file(run_env)
        if env_path:
            load_dotenv(env_path)
            print(f'加载配置文件: {env_path}')
        else:
            env_filename = f'.env.{run_env}' if run_env else '.env.dev'
            print(f'警告: 未找到 {env_filename} 配置文件，使用默认配置')
        print(f'当前cwd: {os.getcwd()}')


# 实例化获取配置类
get_config = GetConfig()
# 应用配置
AppConfig = get_config.get_app_config()
# Jwt配置
JwtConfig = get_config.get_jwt_config()
# 数据库配置
DataBaseConfig = get_config.get_database_config()
# Redis配置
RedisConfig = get_config.get_redis_config()
# 日志配置
LogConfig = get_config.get_log_config()
# 传输层加解密配置
TransportCryptoConfig = get_config.get_transport_crypto_config()
# 上传配置
UploadConfig = get_config.get_upload_config()
# MineU配置
MinerUConfig = get_config.get_mineru_config()
# crawl4ai 爬取引擎配置
Crawl4aiConfig = get_config.get_crawl4ai_config()
# 模型功能适配配置
AiModelFunctionAdapterConfig = get_config.get_ai_model_function_adapter_config()
# 分布式信号量配置
SemaphoreConfig = get_config.get_semaphore_config()
# 网页爬取Agent配置
CrawlerAgentConfig = get_config.get_crawler_agent_config()
# MinIO配置
MinioConfig = get_config.get_minio_config()
# 消息流后端配置
MessageStreamConfig = get_config.get_message_stream_config()
# Stream topic 配置
StreamTopicConfig = get_config.get_stream_topic_config()
