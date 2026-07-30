from typing import Any

from fastapi import Request
from redis import asyncio as aioredis

from knowledge_common.common.constant import CommonConstant
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import CrudResponseModel, PageModel
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.redis.key import RedisKey
from knowledge_common.mapper.dao.config_dao import ConfigDao
from knowledge_common.vo.config_vo import ConfigModel, ConfigPageQueryModel, DeleteConfigModel
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.utils.excel_util import ExcelUtil


class ConfigService:
    """
    参数配置管理模块服务层
    """

    @classmethod
    async def get_config_list_services(
        cls, query_object: ConfigPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取参数配置列表信息service

        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 参数配置列表信息对象
        """
        config_list_result = await ConfigDao.get_config_list(query_object, is_page)

        return config_list_result

    @classmethod
    async def init_cache(cls, redis: aioredis.Redis) -> None:
        """
        应用启动时缓存参数配置表（供 server.py 生命周期调用）

        :param redis: redis对象
        :return:
        """
        await cls.init_cache_sys_config_services(redis)

    @classmethod
    async def init_cache_sys_config_services(cls, redis: aioredis.Redis) -> None:
        """
        应用初始化：获取所有参数配置对应的键值对信息并缓存service

        :param redis: redis对象
        :return:
        """
        # 获取以sys_config:开头的键列表
        keys = await redis.keys(f'{RedisKey.SYS_CONFIG}:*')
        # 删除匹配的键
        if keys:
            await redis.delete(*keys)
        config_all = await ConfigDao.get_config_list(ConfigPageQueryModel(), is_page=False)
        for config_obj in config_all:
            await redis.set(
                f'{RedisKey.SYS_CONFIG}:{config_obj.get("configKey")}',
                config_obj.get('configValue'),
            )

    @classmethod
    async def query_config_list_from_cache_services(cls, redis: aioredis.Redis, config_key: str) -> Any:
        """
        从缓存获取参数键名对应值service

        :param redis: redis对象
        :param config_key: 参数键名
        :return: 参数键名对应值
        """
        result = await redis.get(f'{RedisKey.SYS_CONFIG}:{config_key}')

        return result

    @classmethod
    async def check_config_key_unique_services(cls, page_object: ConfigModel | None = None) -> bool:
        """
        校验参数键名是否唯一service

        :param page_object: 参数配置对象
        :return: 校验结果
        """
        config_id = -1 if page_object.config_id is None else page_object.config_id
        config = await ConfigDao.get_config_detail_by_info(ConfigModel(configKey=page_object.config_key))
        if config and config.config_id != config_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    @transactional()
    async def add_config_services(
        cls, request: Request, page_object: ConfigModel | None = None
    ) -> CrudResponseModel:
        """
        新增参数配置信息service

        :param request: Request对象
        :param page_object: 新增参数配置对象
        :return: 新增参数配置校验结果
        """
        if not await cls.check_config_key_unique_services(page_object):
            raise ServiceException(message=f'新增参数{page_object.config_name}失败，参数键名已存在')
        await ConfigDao.add_config_dao(page_object)
        await request.app.state.redis.set(
            f'{RedisKey.SYS_CONFIG}:{page_object.config_key}', page_object.config_value
        )
        return CrudResponseModel(is_success=True, message='新增成功')

    @classmethod
    @transactional()
    async def edit_config_services(
        cls, request: Request, page_object: ConfigModel
    ) -> CrudResponseModel:
        """
        编辑参数配置信息service

        :param request: Request对象
        :param page_object: 编辑参数配置对象
        :return: 编辑参数配置校验结果
        """
        edit_config = page_object.model_dump(exclude_unset=True)
        config_info = await cls.config_detail_services(page_object.config_id)
        if config_info.config_id:
            if not await cls.check_config_key_unique_services(page_object):
                raise ServiceException(message=f'修改参数{page_object.config_name}失败，参数键名已存在')
            await ConfigDao.edit_config_dao(edit_config)
            if config_info.config_key != page_object.config_key:
                await request.app.state.redis.delete(
                    f'{RedisKey.SYS_CONFIG}:{config_info.config_key}'
                )
            await request.app.state.redis.set(
                f'{RedisKey.SYS_CONFIG}:{page_object.config_key}', page_object.config_value
            )
            return CrudResponseModel(is_success=True, message='更新成功')
        else:
            raise ServiceException(message='参数配置不存在')

    @classmethod
    @transactional()
    async def delete_config_services(
        cls, request: Request, page_object: DeleteConfigModel
    ) -> CrudResponseModel:
        """
        删除参数配置信息service

        :param request: Request对象
        :param page_object: 删除参数配置对象
        :return: 删除参数配置校验结果
        """
        if page_object.config_ids:
            config_id_list = page_object.config_ids.split(',')
            delete_config_key_list = []
            for config_id in config_id_list:
                config_info = await cls.config_detail_services(int(config_id))
                if config_info.config_type == CommonConstant.YES:
                    raise ServiceException(message=f'内置参数{config_info.config_key}不能删除')
                await ConfigDao.delete_config_dao(ConfigModel(configId=int(config_id)))
                delete_config_key_list.append(f'{RedisKey.SYS_CONFIG}:{config_info.config_key}')
            if delete_config_key_list:
                await request.app.state.redis.delete(*delete_config_key_list)
            return CrudResponseModel(is_success=True, message='删除成功')
        else:
            raise ServiceException(message='传入参数配置id为空')

    @classmethod
    async def config_detail_services(cls, config_id: int | None = None) -> ConfigModel:
        """
        获取参数配置详细信息service

        :param config_id: 参数配置id
        :return: 参数配置id对应的信息
        """
        config = await ConfigDao.get_config_detail_by_id(config_id=config_id)
        result = ConfigModel(**CamelCaseUtil.transform_result(config)) if config else ConfigModel()

        return result

    @staticmethod
    async def export_config_list_services(config_list: list) -> bytes:
        """
        导出参数配置信息service

        :param config_list: 参数配置信息列表
        :return: 参数配置信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'configId': '参数主键',
            'configName': '参数名称',
            'configKey': '参数键名',
            'configValue': '参数键值',
            'configType': '系统内置',
            'createBy': '创建者',
            'createTime': '创建时间',
            'updateBy': '更新者',
            'updateTime': '更新时间',
            'remark': '备注',
        }

        for item in config_list:
            if item.get('configType') == 'Y':
                item['configType'] = '是'
            else:
                item['configType'] = '否'
        binary_data = ExcelUtil.export_list2excel(config_list, mapping_dict)

        return binary_data

    @classmethod
    @transactional()
    async def refresh_sys_config_services(cls, request: Request) -> CrudResponseModel:
        """
        刷新字典缓存信息service

        :param request: Request对象
        :return: 刷新字典缓存校验结果
        """
        await cls.init_cache_sys_config_services(request.app.state.redis)

        return CrudResponseModel(is_success=True, message='刷新成功')
