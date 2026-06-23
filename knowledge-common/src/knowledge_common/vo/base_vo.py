from pydantic import BaseModel, Field

from knowledge_common.common.context import RequestContext
from knowledge_common.exceptions.exception import LoginException
from knowledge_common.vo.user_vo import CurrentUserModel


def _safe_get_current_user() -> CurrentUserModel | None:
    try:
        return RequestContext.get_current_user()
    except LoginException:
        return None


class BaseVo(BaseModel):
    userInfo: CurrentUserModel | None = Field(
        default_factory=lambda: _safe_get_current_user(),
        description="用户信息",
    )


__all__ = [
    'BaseVo',
]