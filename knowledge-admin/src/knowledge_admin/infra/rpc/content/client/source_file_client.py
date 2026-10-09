"""admin → knowledge-content 原文文件目录。"""
from __future__ import annotations

from knowledge_common.common.feign import FeignDataVo, feign_client, get_mapping
from knowledge_common.config.env import RpcClientConfig
from knowledge_common.facade.api.knowledge_content.source_file_vo import SourceMarkdownFileListVo


@feign_client(
    name=RpcClientConfig.knowledge_content_service_name,
    # 进程直接挂裸路由；APP_ROOT_PATH 只给网关和文档，直连再拼会 404
    path='',
    url=RpcClientConfig.knowledge_content_url,
    timeout=60,
)
class SourceFileClient:
    """按 doc_id 取解析后 Markdown 的对象键。方法体不执行。"""

    @get_mapping('/internal/documents/{doc_id}/source-files')
    async def list_source_files(cls, doc_id: int) -> FeignDataVo[SourceMarkdownFileListVo]:
        """列出原文文件的 MinIO 对象键"""
