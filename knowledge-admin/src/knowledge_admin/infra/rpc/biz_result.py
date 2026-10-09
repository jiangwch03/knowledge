"""跨服务响应的业务码校验。"""

from __future__ import annotations

from knowledge_common.common.constant import HttpStatusConstant
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger


def ensure_business_ok(code: int | None, msg: str, *, loc: str) -> None:
    """业务码不是成功时打日志并抛出业务异常。"""
    if code == HttpStatusConstant.SUCCESS:
        return
    logger.error('[{}] 业务码异常 code={} msg={}', loc, code, msg)
    detail = msg or f'业务处理失败 code={code}'
    raise ServiceException(message=f'[{loc}] {detail}')
