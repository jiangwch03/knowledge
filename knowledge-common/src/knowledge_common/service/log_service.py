import hashlib
import uuid
from typing import Any

from fastapi import Request

from knowledge_common.common.context import RedisContext
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import CrudResponseModel, PageModel
from knowledge_common.config.env import AppConfig, LogConfig
from knowledge_common.mapper.dao.log_dao import LoginLogDao, OperationLogDao
from knowledge_common.vo.log_vo import (
    DeleteLoginLogModel,
    DeleteOperLogModel,
    LogininforModel,
    LoginLogPageQueryModel,
    OperLogModel,
    OperLogPageQueryModel,
    UnlockUser,
)
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.message_stream import MessageStreamService
from knowledge_common.middlewares.trace_middleware.ctx import TraceCtx
from knowledge_common.service.dict_service import DictDataService
from knowledge_common.utils.excel_util import ExcelUtil
from knowledge_common.utils.log_util import LogSanitizer


class OperationLogService:
    """
    操作日志管理模块服务层
    """

    @classmethod
    async def get_operation_log_list_services(
        cls, query_object: OperLogPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取操作日志列表信息service

        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 操作日志列表信息对象
        """
        operation_log_list_result = await OperationLogDao.get_operation_log_list(query_object, is_page)

        return operation_log_list_result

    @classmethod
    @transactional()
    async def add_operation_log_services(cls, page_object: OperLogModel) -> CrudResponseModel:
        """
        新增操作日志service

        :param page_object: 新增操作日志对象
        :return: 新增操作日志校验结果
        """
        await OperationLogDao.add_operation_log_dao(page_object)
        return CrudResponseModel(is_success=True, message='新增成功')

    @classmethod
    @transactional()
    async def delete_operation_log_services(
        cls, page_object: DeleteOperLogModel
    ) -> CrudResponseModel:
        """
        删除操作日志信息service

        :param page_object: 删除操作日志对象
        :return: 删除操作日志校验结果
        """
        if page_object.oper_ids:
            oper_id_list = page_object.oper_ids.split(',')
            for oper_id in oper_id_list:
                await OperationLogDao.delete_operation_log_dao(OperLogModel(operId=oper_id))
            return CrudResponseModel(is_success=True, message='删除成功')
        else:
            raise ServiceException(message='传入操作日志id为空')

    @classmethod
    @transactional()
    async def clear_operation_log_services(cls) -> CrudResponseModel:
        """
        清除操作日志信息service

        :return: 清除操作日志校验结果
        """
        await OperationLogDao.clear_operation_log_dao()
        return CrudResponseModel(is_success=True, message='清除成功')

    @classmethod
    async def export_operation_log_list_services(cls, request: Request, operation_log_list: list) -> bytes:
        """
        导出操作日志信息service

        :param request: Request对象
        :param operation_log_list: 操作日志信息列表
        :return: 操作日志信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'operId': '日志编号',
            'title': '系统模块',
            'businessType': '操作类型',
            'method': '方法名称',
            'requestMethod': '请求方式',
            'operName': '操作人员',
            'deptName': '部门名称',
            'operUrl': '请求URL',
            'operIp': '操作地址',
            'operLocation': '操作地点',
            'operParam': '请求参数',
            'jsonResult': '返回参数',
            'status': '操作状态',
            'error_msg': '错误消息',
            'operTime': '操作日期',
            'costTime': '消耗时间（毫秒）',
        }

        operation_type_list = await DictDataService.query_dict_data_list_from_cache_services(
            request.app.state.redis, dict_type='sys_oper_type'
        )
        operation_type_option = [
            {'label': item.get('dictLabel'), 'value': item.get('dictValue')} for item in operation_type_list
        ]
        operation_type_option_dict = {item.get('value'): item for item in operation_type_option}

        for item in operation_log_list:
            if item.get('status') == 0:
                item['status'] = '成功'
            else:
                item['status'] = '失败'
            if str(item.get('businessType')) in operation_type_option_dict:
                item['businessType'] = operation_type_option_dict.get(str(item.get('businessType'))).get('label')
        binary_data = ExcelUtil.export_list2excel(operation_log_list, mapping_dict)

        return binary_data


class LoginLogService:
    """
    登录日志管理模块服务层
    """

    @classmethod
    async def get_login_log_list_services(
        cls, query_object: LoginLogPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取登录日志列表信息service

        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 登录日志列表信息对象
        """
        operation_log_list_result = await LoginLogDao.get_login_log_list(query_object, is_page)

        return operation_log_list_result

    @classmethod
    @transactional()
    async def add_login_log_services(cls, page_object: LogininforModel) -> CrudResponseModel:
        """
        新增登录日志service

        :param page_object: 新增登录日志对象
        :return: 新增登录日志校验结果
        """
        await LoginLogDao.add_login_log_dao(page_object)
        return CrudResponseModel(is_success=True, message='新增成功')

    @classmethod
    @transactional()
    async def delete_login_log_services(
        cls, page_object: DeleteLoginLogModel
    ) -> CrudResponseModel:
        """
        删除操作日志信息service

        :param page_object: 删除操作日志对象
        :return: 删除操作日志校验结果
        """
        if page_object.info_ids:
            info_id_list = page_object.info_ids.split(',')
            for info_id in info_id_list:
                await LoginLogDao.delete_login_log_dao(LogininforModel(infoId=info_id))
            return CrudResponseModel(is_success=True, message='删除成功')
        else:
            raise ServiceException(message='传入登录日志id为空')

    @classmethod
    @transactional()
    async def clear_login_log_services(cls) -> CrudResponseModel:
        """
        清除操作日志信息service

        :return: 清除操作日志校验结果
        """
        await LoginLogDao.clear_login_log_dao()
        return CrudResponseModel(is_success=True, message='清除成功')

    @classmethod
    async def unlock_user_services(cls, request: Request, unlock_user: UnlockUser) -> CrudResponseModel:
        locked_user = await request.app.state.redis.get(f'account_lock:{unlock_user.user_name}')
        if locked_user:
            await request.app.state.redis.delete(f'account_lock:{unlock_user.user_name}')
            return CrudResponseModel(is_success=True, message='解锁成功')
        raise ServiceException(message='该用户未锁定')

    @staticmethod
    async def export_login_log_list_services(login_log_list: list) -> bytes:
        """
        导出登录日志信息service

        :param login_log_list: 登录日志信息列表
        :return: 登录日志信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'infoId': '访问编号',
            'userName': '用户名称',
            'ipaddr': '登录地址',
            'loginLocation': '登录地点',
            'browser': '浏览器',
            'os': '操作系统',
            'status': '登录状态',
            'msg': '操作信息',
            'loginTime': '登录日期',
        }

        for item in login_log_list:
            if item.get('status') == '0':
                item['status'] = '成功'
            else:
                item['status'] = '失败'
        binary_data = ExcelUtil.export_list2excel(login_log_list, mapping_dict)

        return binary_data


class LogQueueService:
    """
    日志队列服务

    职责：把登录日志 / 操作日志推送到 MessageStreamService（topic 按 app_name 隔离）。
    业务幂等键 event_id 进入 headers，消费者侧由 LogDedupHelper 保证一次性落库。
    """

    @classmethod
    def _build_event_id(cls, request_id: str, log_type: str, source: str) -> str:
        """
        生成日志事件唯一标识

        :param request_id: 请求唯一标识
        :param log_type: 日志类型
        :param source: 日志来源
        :return: 事件唯一标识
        """
        if not request_id:
            return uuid.uuid4().hex
        base = f'{request_id}:{log_type}:{source}'
        return hashlib.md5(base.encode('utf-8')).hexdigest()

    @classmethod
    async def enqueue_login_log(cls, request: Request, login_log: LogininforModel, source: str) -> None:
        """
        登录日志入队（通过 MessageStreamService.produce 推送到 log:login:{app_name}）

        :param request: Request对象
        :param login_log: 登录日志模型
        :param source: 日志来源
        :return: None
        """
        app_name = cls._resolve_app_name(request)
        payload = LogSanitizer.sanitize_data(login_log.model_dump(by_alias=True, exclude_none=True))
        await cls._produce_event(event_type='login', payload=payload, source=source, app_name=app_name)

    @classmethod
    async def enqueue_operation_log(cls, request: Request, operation_log: OperLogModel, source: str) -> None:
        """
        操作日志入队（通过 MessageStreamService.produce 推送到 log:operation:{app_name}）

        :param request: Request对象
        :param operation_log: 操作日志模型
        :param source: 日志来源
        :return: None
        """
        app_name = cls._resolve_app_name(request)
        payload = LogSanitizer.sanitize_data(operation_log.model_dump(by_alias=True, exclude_none=True))
        await cls._produce_event(event_type='operation', payload=payload, source=source, app_name=app_name)

    @classmethod
    async def _produce_event(
        cls, event_type: str, payload: dict, source: str, app_name: str
    ) -> None:
        """
        通过 MessageStreamService 推送日志事件

        topic 命名：log:{event_type}:{app_name}（按 app_name 自产自销）
        key 用 request_id（保证 Redis stream 内顺序、Kafka 内同 partition）
        headers 携带 event_id 等元数据，消费者侧用 event_id 做业务级去重

        :param event_type: 事件类型（login / operation）
        :param payload: 已脱敏的事件载荷
        :param source: 日志来源
        :param app_name: 应用标识（topic 按 app_name 隔离）
        :return: None
        """
        request_id = TraceCtx.get_request_id()
        trace_id = TraceCtx.get_trace_id()
        span_id = TraceCtx.get_span_id()
        event_id = cls._build_event_id(request_id, event_type, source)
        headers = {
            'event_id': event_id,
            'event_type': event_type,
            'request_id': request_id,
            'trace_id': trace_id,
            'span_id': span_id,
            'app_name': app_name,
            'source': source,
        }
        topic = f'log:{event_type}:{app_name}'
        await MessageStreamService.produce(
            topic=topic,
            value=payload,
            key=request_id,
            headers=headers,
        )

    @staticmethod
    def _resolve_app_name(request: Request) -> str:
        """
        解析当前请求所属的应用名（用于日志「自产自销」隔离）

        优先从 request.app.state.app_name 取（lifespan 中设置），fallback 到 AppConfig.app_name。
        """
        return getattr(request.app.state, 'app_name', None) or AppConfig.app_name


class LogDedupHelper:
    """
    业务级日志去重 helper（基于 Redis SET NX EX）

    用 async with 上下文管理器包装「acquire → 业务 → 异常释放」语义，业务侧零踩坑：

        async with LogDedupHelper.acquire(event_id, app_name) as ok:
            if not ok:
                return  # 已被其他消费者落库（重复消息）或 event_id 为空，直接跳过
            async with AsyncSessionLocal() as session:
                await SomeLogDao.add_xxx_dao(session, ...)
                await session.commit()

    语义：
    - __aenter__：调 ``redis.set(key, '1', nx=True, ex=LogConfig.log_stream_dedup_ttl)``，
      返回是否首次获取（True = 首次成功，False = key 已存在 / event_id 为空）
    - __aexit__：
      - 业务正常返回 → 保留 TTL 内的去重窗口（避免短期重复落库）
      - 业务抛异常 → 主动 delete dedup key（对应原 _release_dedup 行为），
        允许后端协议下一轮重试时再次获取
    """

    @classmethod
    def acquire(cls, event_id: str, app_name: str) -> '_DedupAcquireCtx':
        """
        创建去重 async context manager

        :param event_id: 业务幂等键（md5(request_id+log_type+source)），空值时永远返回 False
        :param app_name: 应用标识（dedup key 按 app 隔离）
        :return: async context manager 实例
        """
        return _DedupAcquireCtx(event_id=event_id, app_name=app_name)


class _DedupAcquireCtx:
    """
    LogDedupHelper.acquire 返回的内部 async context manager

    职责：在 Redis 上 SET NX EX 一个去重 key，业务异常时主动释放。
    业务方应通过 ``async with LogDedupHelper.acquire(...) as ok:`` 使用，
    不应直接实例化本类。
    """

    def __init__(self, *, event_id: str, app_name: str) -> None:
        self._event_id = event_id
        self._app_name = app_name
        self._acquired = False

    @property
    def _key(self) -> str:
        return f'{LogConfig.get_dedup_prefix(self._app_name)}:{self._event_id}'

    async def __aenter__(self) -> bool:
        # 空 event_id 直接返回 False（与原 _acquire_dedup 行为一致：不写 key，调用方应跳过业务）
        if not self._event_id:
            return False
        redis = RedisContext.get_redis()
        result = await redis.set(self._key, '1', nx=True, ex=LogConfig.log_stream_dedup_ttl)
        self._acquired = bool(result)
        return self._acquired

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # 仅在 acquire 成功 + 业务抛异常时释放（对应原 _release_dedup 语义）
        if not self._acquired:
            return
        if exc_type is None:
            # 正常完成：保留 TTL 内的去重窗口（避免短期重复落库）
            return
        # 异常分支：释放 dedup key，允许后端协议下一轮重试时再次落库
        try:
            redis = RedisContext.get_redis()
            await redis.delete(self._key)
        except Exception:
            # 释放失败不影响异常向上传播
            pass


__all__ = [
    'OperationLogService',
    'LoginLogService',
    'LogQueueService',
    'LogDedupHelper',
]
