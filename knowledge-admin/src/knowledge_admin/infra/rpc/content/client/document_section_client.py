"""admin → knowledge-content 出题切节。"""
from __future__ import annotations

from knowledge_common.common.feign import FeignDataVo, feign_client, get_mapping
from knowledge_common.config.env import RpcClientConfig
from knowledge_common.facade.api.knowledge_content.document_section_vo import DocumentSectionListVo


@feign_client(
    name=RpcClientConfig.knowledge_content_service_name,
    # 进程直接挂裸路由；APP_ROOT_PATH 只给网关和文档，直连再拼会 404
    path='',
    url=RpcClientConfig.knowledge_content_url,
    timeout=60,
)
class DocumentSectionClient:
    """按 doc_id 取上传文档切好的节。方法体不执行。"""

    @get_mapping('/internal/documents/{doc_id}/sections')
    async def list_sections(cls, doc_id: int) -> FeignDataVo[DocumentSectionListVo]:
        """列出按标题或字数切出的节"""
