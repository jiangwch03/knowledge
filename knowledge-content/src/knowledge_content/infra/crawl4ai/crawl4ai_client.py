"""crawl4ai 爬取引擎客户端门面

根据 Crawl4aiConfig.crawl4ai_mode 配置自动分发到对应实现：
- sdk: 本地 SDK 模式（_Crawl4aiSdkClient），进程内直接调用 crawl4ai Python 库
- service: 远程服务模式（_Crawl4aiServiceClient），通过 HTTP 调用独立部署的 crawl4ai Docker 服务

业务层统一通过 Crawl4aiClient.crawl() 或 Crawl4aiClient.crawl_stream() 调用，无需关心底层实现。
切换模式只需修改 .env 中的 crawl4ai_mode 即可。
"""

from collections.abc import AsyncIterator

from knowledge_common.config.env import Crawl4aiConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.strategy_config_resolver import (
    merge_hook_params,
    resolve_strategy_config,
)
from knowledge_content.infra.crawl4ai._crawl4ai_config_builder import Crawl4aiConfigBuilder
from knowledge_content.infra.crawl4ai.vo.crawl4ai_vo import CrawlResultVo
from knowledge_content.infra.crawl4ai._crawl4ai_sdk_client import _Crawl4aiSdkClient
from knowledge_content.infra.crawl4ai._crawl4ai_service_client import _Crawl4aiServiceClient
# 支持的调用模式
_MODE_SDK: str = 'sdk'
_MODE_SERVICE: str = 'service'
_VALID_MODES: set[str] = {_MODE_SDK, _MODE_SERVICE}


class Crawl4aiClient:
    """
    crawl4ai 爬取引擎统一客户端

    门面模式：根据配置将请求分发到 SDK 实现或 Service 实现，
    对外暴露统一的 crawl_stream() 接口，返回类型化的 CrawlResultVo。
    所有方法均为 @classmethod，无状态设计。
    """

    @classmethod
    def _prepare_crawler_run_config(cls, strategy_config: dict | None) -> dict:
        """拆分 strategy_config 并合并 hooks 转换结果"""
        _, crawler_run_config, hooks = resolve_strategy_config(strategy_config)
        return merge_hook_params(crawler_run_config, hooks)

    @classmethod
    def validate_config(cls, crawl_config: dict) -> None:
        """
        校验爬取配置参数是否可被正确转换，不触发实际爬取。

        根据当前 crawl4ai_mode 走对应的 ConfigBuilder 转换路径，
        确保 LLM 生成的配置参数名、嵌套结构、类型能被正常解析。
        参数转换没问题即视为校验通过（即使有默认值兜底也属于可正常转换）。

        :param crawl_config: LLM 生成的爬取配置（可为完整 strategy_config 或扁平 crawler_run_config）
        :raises ServiceException: 参数转换失败时抛出
        """
        prepared = cls._prepare_crawler_run_config(crawl_config)
        mode = Crawl4aiConfig.crawl4ai_mode
        if mode == _MODE_SDK:
            # SDK 模式：构建 Python 对象（校验更严格，会实际导入 crawl4ai 类构造）
            Crawl4aiConfigBuilder.build_crawl_config(prepared)
        else:
            # Service 模式：序列化为 Docker API {type, params} 格式
            Crawl4aiConfigBuilder.serialize_crawl_config(prepared)

    @classmethod
    async def crawl_stream(cls, target_url: str, crawl_config: dict | None = None) -> AsyncIterator[CrawlResultVo]:
        """
        流式爬取（统一入口），每爬完一个页面立即 yield 结果

        根据 crawl4ai_mode 配置自动选择 SDK 或 Service 模式执行流式爬取。
        SDK 模式为真正的逐页 yield；Service 模式因 HTTP API 限制，内部全量接收后逐个 yield。

        :param target_url: 目标 URL
        :param crawl_config: LLM 生成的策略配置
        :return: 异步生成器，逐个产出 CrawlResultVo
        :raises ServiceException: 配置了无效模式时抛出
        """
        mode = Crawl4aiConfig.crawl4ai_mode

        if mode not in _VALID_MODES:
            raise ServiceException(
                message=f'无效的 crawl4ai_mode: {mode}，支持值: {_VALID_MODES}'
            )

        prepared_config = cls._prepare_crawler_run_config(crawl_config)
        logger.info(f'[Crawl4aiClient] 使用 {mode} 模式流式爬取: url={target_url}')

        if mode == _MODE_SDK:
            # SDK 模式：真正流式，爬完一个 yield 一个
            async for result in _Crawl4aiSdkClient.crawl_stream(target_url, prepared_config):
                yield result
        else:
            # Service 模式：通过 POST /crawl/stream 接收 NDJSON 流，逐行 yield
            async for result in _Crawl4aiServiceClient.crawl_stream(target_url, prepared_config):
                yield result

    @classmethod
    async def probe_page(cls, target_url: str, crawl_config: dict | None = None) -> dict:
        """
        轻量浏览器渲染探针（单页，不触发深度爬取）

        :param target_url: 目标 URL
        :param crawl_config: 可选策略片段（hooks / crawler_run_config），用于登录后复探
        :return: {success, title, html, visible_text, error, ...}
        """
        mode = Crawl4aiConfig.crawl4ai_mode
        if mode == _MODE_SDK:
            return await _Crawl4aiSdkClient.probe_page(target_url, crawl_config)
        return await _Crawl4aiServiceClient.probe_page(target_url, crawl_config)
