from knowledge_common.config.env import MinerUConfig
from pydantic import BaseModel, Field

from knowledge_rag.enums.mineru_enum import MinerUParseModeEnum


class MinerUClientConfig(BaseModel):
    """MineU 客户端配置 Bean，内部读取 .env.dev"""

    base_url: str = MinerUConfig.mineru_url
    file_urls_uri: str = MinerUConfig.mineru_file_urls_uri
    extract_results_uri: str = MinerUConfig.mineru_extract_results_uri
    token: str = MinerUConfig.mineru_token
    default_model_version: str = MinerUConfig.mineru_model_version
    html_model_version: str = MinerUConfig.mineru_html_model_version
    callback_url: str = MinerUConfig.mineru_callback_url
    seed: str = MinerUConfig.mineru_seed

    def resolve_model_version(self, parse_mode: MinerUParseModeEnum) -> str:
        mapping = {
            MinerUParseModeEnum.NORMAL: self.default_model_version,
            MinerUParseModeEnum.HTML: self.html_model_version,
        }
        if parse_mode not in mapping:
            raise ValueError(f'不支持的解析模式: {parse_mode.value}')
        return mapping[parse_mode]

# 单例实例化
minerUClientConfig = MinerUClientConfig()

__all__ = [
    'minerUClientConfig'
]
