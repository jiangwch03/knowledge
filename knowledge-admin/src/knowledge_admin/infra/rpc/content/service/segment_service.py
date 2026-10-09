"""调用 knowledge-content 分段 Client，统一日志与异常。"""

from __future__ import annotations

from knowledge_common.common.feign import FeignPageVo
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.facade.api.knowledge_content.segment_facade_vo import (
    SegmentFullItemVo,
    SegmentListQuery,
)
from knowledge_common.utils.log_util import logger

from knowledge_admin.infra.rpc.biz_result import ensure_business_ok
from knowledge_admin.infra.rpc.content.client.segment_client import SegmentClient


class SegmentService:
    """分段全文分页。"""

    @classmethod
    async def page_full(cls, query: SegmentListQuery) -> FeignPageVo[SegmentFullItemVo]:
        """按文档分页拉取分段正文。"""
        loc = f'{cls.__name__}.page_full'
        try:
            page = await SegmentClient.page_full(query)
            ensure_business_ok(page.code, page.msg, loc=loc)
        except ServiceException:
            raise
        except Exception as e:
            logger.exception(
                '[{}] 分页拉取分段正文失败 doc_id={} page={}/{} error={}',
                loc,
                query.doc_id,
                query.page_num,
                query.page_size,
                e,
            )
            raise ServiceException(message=f'[{loc}] 拉取文档分段失败: {e}') from e
        logger.info(
            '[{}] 分页拉取分段正文成功 doc_id={} page={}/{} rows={} total={}',
            loc,
            query.doc_id,
            query.page_num,
            query.page_size,
            len(page.rows),
            page.total,
        )
        return page
