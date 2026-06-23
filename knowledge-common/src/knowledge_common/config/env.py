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
    group_id: str = 'knowledge_rag'
    # 文档解析待处理队列
    document_parse_pending: str = 'document.parse.pending'
    # 文档 Markdown 合并待处理队列
    document_md_pending: str = 'document.md.pending'

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


def _resolve_workspace_root() -> str | None:
    """
    从 knowledge_common 包位置回溯 workspace 根目录
    """
    try:
        # env.py 位于 knowledge-common/src/knowledge_common/config/env.py
        # 回溯 3 层到达 knowledge-common/，再上一层即为 workspace 根
        env_dir = os.path.dirname(os.path.abspath(__file__))
        knowledge_common_dir = os.path.dirname(os.path.dirname(os.path.dirname(env_dir)))
        workspace_root = os.path.dirname(knowledge_common_dir)
        if os.path.isdir(workspace_root):
            return workspace_root
    except Exception:
        pass
    return None


def _infer_current_project() -> str | None:
    """
    根据 sys.argv 推断当前启动的是哪个子项目
    """
    argv_str = ' '.join(sys.argv)
    if 'knowledge_admin' in argv_str or 'knowledge-admin' in argv_str:
        return 'knowledge-admin'
    if 'knowledge_rag' in argv_str or 'knowledge-rag' in argv_str:
        return 'knowledge-rag'
    return None


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
    workspace_root = _resolve_workspace_root()
    current_project = _infer_current_project()
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
# MinIO配置
MinioConfig = get_config.get_minio_config()
# 消息流后端配置
MessageStreamConfig = get_config.get_message_stream_config()
# Stream topic 配置
StreamTopicConfig = get_config.get_stream_topic_config()
