"""admin → knowledge-content 分段全文分页。"""

from __future__ import annotations

from knowledge_common.common.feign import FeignPageVo, feign_client, get_mapping
from knowledge_common.config.env import RpcClientConfig
from knowledge_common.facade.api.knowledge_content.segment_facade_vo import (
    SegmentFullItemVo,
    SegmentListQuery,
)


@feign_client(
    name=RpcClientConfig.knowledge_content_service_name,
    # 进程直接挂裸路由；APP_ROOT_PATH 只给网关和文档，直连再拼会 404
    path='',
    url=RpcClientConfig.knowledge_content_url,
    timeout=120,
)
class SegmentClient:
    """按 doc_id 分页拉取分段正文。方法体不执行。"""

    @get_mapping('/internal/segments')
    async def page_full(cls, query: SegmentListQuery) -> FeignPageVo[SegmentFullItemVo]:
        """拉取文档分段"""
