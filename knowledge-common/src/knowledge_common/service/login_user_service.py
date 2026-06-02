from datetime import timedelta

import jwt
from fastapi import Depends, Form, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from knowledge_common.dao.user_login_dao import UserDao
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_common.common.context import RequestContext
from knowledge_common.common.enums import RedisInitKeyConfig
from knowledge_common.config.env import AppConfig, JwtConfig
from knowledge_common.config.get_db import get_db
from knowledge_common.entity.vo.user_vo import CurrentUserModel, TokenData, UserInfoModel
from knowledge_common.exceptions.exception import AuthException
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.utils.log_util import logger

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='login')

class LoginUserService:

    @classmethod
    async def get_current_user(
        cls, request: Request = Request, token: str = Depends(oauth2_scheme), query_db: AsyncSession = Depends(get_db)
    ) -> CurrentUserModel:
        """
        根据token获取当前用户信息

        :param request: Request对象
        :param token: 用户token
        :param query_db: orm对象
        :return: 当前用户信息对象
        :raise: 令牌异常AuthException
        """
        # if token[:6] != 'Bearer':
        #     logger.warning("用户token不合法")
        #     raise AuthException(data="", message="用户token不合法")
        try:
            if token.startswith('Bearer'):
                token = token.split(' ')[1]
            payload = jwt.decode(token, JwtConfig.jwt_secret_key, algorithms=[JwtConfig.jwt_algorithm])
            user_id: str = payload.get('user_id')
            session_id: str = payload.get('session_id')
            if not user_id:
                logger.warning('用户token不合法')
                raise AuthException(data='', message='用户token不合法')
            token_data = TokenData(user_id=int(user_id))
        except InvalidTokenError as e:
            logger.warning('用户token已失效，请重新登录')
            raise AuthException(data='', message='用户token已失效，请重新登录') from e
        query_user = await UserDao.get_user_by_id(query_db, user_id=token_data.user_id)
        if query_user.get('user_basic_info') is None:
            logger.warning('用户token不合法')
            raise AuthException(data='', message='用户token不合法')
        if AppConfig.app_same_time_login:
            redis_token = await request.app.state.redis.get(f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}')
        else:
            # 此方法可实现同一账号同一时间只能登录一次
            redis_token = await request.app.state.redis.get(
                f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{query_user.get("user_basic_info").user_id}'
            )
        if token == redis_token:
            if AppConfig.app_same_time_login:
                await request.app.state.redis.set(
                    f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}',
                    redis_token,
                    ex=timedelta(minutes=JwtConfig.jwt_redis_expire_minutes),
                )
            else:
                await request.app.state.redis.set(
                    f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{query_user.get("user_basic_info").user_id}',
                    redis_token,
                    ex=timedelta(minutes=JwtConfig.jwt_redis_expire_minutes),
                )

            role_id_list = [item.role_id for item in query_user.get('user_role_info')]
            if 1 in role_id_list:  # noqa: SIM108
                permissions = ['*:*:*']
            else:
                permissions = [row.perms for row in query_user.get('user_menu_info')]
            post_ids = ','.join([str(row.post_id) for row in query_user.get('user_post_info')])
            role_ids = ','.join([str(row.role_id) for row in query_user.get('user_role_info')])
            roles = [row.role_key for row in query_user.get('user_role_info')]
            is_default_modify_pwd = await cls.__init_password_is_modify(
                request, query_user.get('user_basic_info').pwd_update_date
            )
            is_password_expired = await cls.__password_is_expired(
                request, query_user.get('user_basic_info').pwd_update_date
            )

            current_user = CurrentUserModel(
                permissions=permissions,
                roles=roles,
                user=UserInfoModel(
                    **CamelCaseUtil.transform_result(query_user.get('user_basic_info')),
                    postIds=post_ids,
                    roleIds=role_ids,
                    dept=CamelCaseUtil.transform_result(query_user.get('user_dept_info')),
                    role=CamelCaseUtil.transform_result(query_user.get('user_role_info')),
                ),
                isDefaultModifyPwd=is_default_modify_pwd,
                isPasswordExpired=is_password_expired,
            )
            # 设置当前用户信息到上下文
            RequestContext.set_current_user(current_user)
            return current_user
        logger.warning('用户token已失效，请重新登录')
        raise AuthException(data='', message='用户token已失效，请重新登录')


















