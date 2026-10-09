"""调用 knowledge-content 原文文件目录。"""
from __future__ import annotations

from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.facade.api.knowledge_content.source_file_vo import SourceMarkdownFileListVo
from knowledge_common.utils.log_util import logger

from knowledge_admin.infra.rpc.biz_result import ensure_business_ok
from knowledge_admin.infra.rpc.content.client.source_file_client import SourceFileClient


class SourceFileService:
    """原文对象键。正文不经过这个接口。"""

    @classmethod
    async def list_source_files(cls, doc_id: int) -> SourceMarkdownFileListVo:
        loc = f'{cls.__name__}.list_source_files'
        try:
            result = await SourceFileClient.list_source_files(doc_id)
            ensure_business_ok(result.code, result.msg, loc=loc)
        except ServiceException:
            raise
        except Exception as e:
            logger.exception('[{}] 查询原文文件失败 doc_id={} error={}', loc, doc_id, e)
            raise ServiceException(message=f'[{loc}] 查询原文文件失败: {e}') from e
        files = result.data.files if result.data is not None else []
        logger.info('[{}] 查询原文文件成功 doc_id={} files={}', loc, doc_id, len(files))
        if result.data is None:
            return SourceMarkdownFileListVo()
        return result.data
