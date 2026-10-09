"""调用 knowledge-content 出题切节。"""
from __future__ import annotations

from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.facade.api.knowledge_content.document_section_vo import DocumentSectionListVo
from knowledge_common.utils.log_util import logger

from knowledge_admin.infra.rpc.biz_result import ensure_business_ok
from knowledge_admin.infra.rpc.content.client.document_section_client import DocumentSectionClient


class DocumentSectionService:
    """上传文档的节。正文由 content 读完再切，admin 不再自己切。"""

    @classmethod
    async def list_sections(cls, doc_id: int) -> DocumentSectionListVo:
        loc = f'{cls.__name__}.list_sections'
        try:
            result = await DocumentSectionClient.list_sections(doc_id)
            ensure_business_ok(result.code, result.msg, loc=loc)
        except ServiceException:
            raise
        except Exception as e:
            logger.exception('[{}] 查询文档切节失败 doc_id={} error={}', loc, doc_id, e)
            raise ServiceException(message=f'[{loc}] 查询文档切节失败: {e}') from e
        logger.info(
            '[{}] 查询文档切节成功 doc_id={} sections={}',
            loc,
            doc_id,
            len(result.data.sections) if result.data is not None else 0,
        )
        if result.data is None:
            return DocumentSectionListVo()
        return result.data
