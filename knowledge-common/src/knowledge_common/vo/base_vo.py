from pydantic import BaseModel, Field, model_validator

from knowledge_common.common.context import RequestContext
from knowledge_common.vo.user_vo import CurrentUserModel


class BaseVo(BaseModel):
    userInfo: CurrentUserModel = Field(description="用户信息")

    @model_validator(mode='after')
    def _fill_user_info(self) -> 'Base_vo':
        if self.userInfo is None:
            self.userInfo = RequestContext.get_current_user()
        return self