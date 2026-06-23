from typing import Any

from fastapi import Request
from knowledge_common.common.constant import CommonConstant, JobConstant
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import CrudResponseModel, PageModel
from knowledge_common.config.get_scheduler import SchedulerUtil
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.job_dao import JobDao
from knowledge_common.service.dict_service import DictDataService
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.utils.cron_util import CronUtil
from knowledge_common.utils.excel_util import ExcelUtil
from knowledge_common.utils.string_util import StringUtil
from knowledge_common.vo.job_vo import DeleteJobModel, EditJobModel, JobModel, JobPageQueryModel


class JobService:
    """
    定时任务管理模块服务层
    """

    @classmethod
    async def get_job_list_services(
        cls, query_object: JobPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取定时任务列表信息service

        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 定时任务列表信息对象
        """
        job_list_result = await JobDao.get_job_list(query_object, is_page)

        return job_list_result

    @classmethod
    async def check_job_unique_services(cls, page_object: JobModel) -> bool:
        """
        校验定时任务是否存在service

        :param page_object: 定时任务对象
        :return: 校验结果
        """
        job_id = -1 if page_object.job_id is None else page_object.job_id
        job = await JobDao.get_job_detail_by_info(page_object)
        if job and job.job_id != job_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    @transactional()
    async def add_job_services(cls, page_object: JobModel) -> CrudResponseModel:
        """
        新增定时任务信息service

        :param page_object: 新增定时任务对象
        :return: 新增定时任务校验结果
        """
        if not CronUtil.validate_cron_expression(page_object.cron_expression):
            raise ServiceException(message=f'新增定时任务{page_object.job_name}失败，Cron表达式不正确')
        if StringUtil.contains_ignore_case(page_object.invoke_target, CommonConstant.LOOKUP_RMI):
            raise ServiceException(message=f'新增定时任务{page_object.job_name}失败，目标字符串不允许rmi调用')
        if StringUtil.contains_any_ignore_case(
            page_object.invoke_target, [CommonConstant.LOOKUP_LDAP, CommonConstant.LOOKUP_LDAPS]
        ):
            raise ServiceException(message=f'新增定时任务{page_object.job_name}失败，目标字符串不允许ldap(s)调用')
        if StringUtil.contains_any_ignore_case(page_object.invoke_target, [CommonConstant.HTTP, CommonConstant.HTTPS]):
            raise ServiceException(message=f'新增定时任务{page_object.job_name}失败，目标字符串不允许http(s)调用')
        if StringUtil.startswith_any_case(page_object.invoke_target, JobConstant.JOB_ERROR_LIST):
            raise ServiceException(message=f'新增定时任务{page_object.job_name}失败，目标字符串存在违规')
        if not StringUtil.startswith_any_case(page_object.invoke_target, JobConstant.JOB_WHITE_LIST):
            raise ServiceException(message=f'新增定时任务{page_object.job_name}失败，目标字符串不在白名单内')
        if not await cls.check_job_unique_services(page_object):
            raise ServiceException(message=f'新增定时任务{page_object.job_name}失败，定时任务已存在')
        add_job = await JobDao.add_job_dao(page_object)
        job_info = await cls.job_detail_services(add_job.job_id)
        await SchedulerUtil.broadcast_scheduler_sync(app_scope=job_info.app_scope)

        return CrudResponseModel(is_success=True, message='新增成功')

    @classmethod
    def _deal_edit_job(cls, page_object: EditJobModel, edit_job: dict[str, Any]) -> None:
        """
        处理编辑定时任务字典

        :param page_object: 编辑定时任务对象
        :param edit_job: 编辑定时任务字典
        """
        if page_object.type == 'status':
            del edit_job['type']

    @classmethod
    @transactional()
    async def edit_job_services(cls, page_object: EditJobModel) -> CrudResponseModel:
        """
        编辑定时任务信息service

        :param page_object: 编辑定时任务对象
        :return: 编辑定时任务校验结果
        """
        edit_job = page_object.model_dump(exclude_unset=True)
        cls._deal_edit_job(page_object, edit_job)
        job_info = await cls.job_detail_services(page_object.job_id)
        if job_info:
            if page_object.type != 'status':
                if not CronUtil.validate_cron_expression(page_object.cron_expression):
                    raise ServiceException(message=f'修改定时任务{page_object.job_name}失败，Cron表达式不正确')
                if StringUtil.contains_ignore_case(page_object.invoke_target, CommonConstant.LOOKUP_RMI):
                    raise ServiceException(message=f'修改定时任务{page_object.job_name}失败，目标字符串不允许rmi调用')
                if StringUtil.contains_any_ignore_case(
                    page_object.invoke_target, [CommonConstant.LOOKUP_LDAP, CommonConstant.LOOKUP_LDAPS]
                ):
                    raise ServiceException(
                        message=f'修改定时任务{page_object.job_name}失败，目标字符串不允许ldap(s)调用'
                    )
                if StringUtil.contains_any_ignore_case(
                    page_object.invoke_target, [CommonConstant.HTTP, CommonConstant.HTTPS]
                ):
                    raise ServiceException(
                        message=f'修改定时任务{page_object.job_name}失败，目标字符串不允许http(s)调用'
                    )
                if StringUtil.startswith_any_case(page_object.invoke_target, JobConstant.JOB_ERROR_LIST):
                    raise ServiceException(message=f'修改定时任务{page_object.job_name}失败，目标字符串存在违规')
                if not StringUtil.startswith_any_case(page_object.invoke_target, JobConstant.JOB_WHITE_LIST):
                    raise ServiceException(message=f'修改定时任务{page_object.job_name}失败，目标字符串不在白名单内')
                if not await cls.check_job_unique_services(page_object):
                    raise ServiceException(message=f'修改定时任务{page_object.job_name}失败，定时任务已存在')
            await JobDao.edit_job_dao(edit_job, job_info)
            await SchedulerUtil.broadcast_scheduler_sync(app_scope=job_info.app_scope)
            return CrudResponseModel(is_success=True, message='更新成功')
        raise ServiceException(message='定时任务不存在')

    @classmethod
    async def execute_job_once_services(cls, page_object: JobModel) -> CrudResponseModel:
        """
        执行一次定时任务service

        :param page_object: 定时任务对象
        :return: 执行一次定时任务结果
        """
        job_info = await cls.job_detail_services(page_object.job_id)
        if job_info:
            await SchedulerUtil.broadcast_execute_job_once(job_id=page_object.job_id, app_scope=job_info.app_scope)
            return CrudResponseModel(is_success=True, message='执行成功')
        raise ServiceException(message='定时任务不存在')

    @classmethod
    @transactional()
    async def delete_job_services(cls, page_object: DeleteJobModel) -> CrudResponseModel:
        """
        删除定时任务信息service

        :param page_object: 删除定时任务对象
        :return: 删除定时任务校验结果
        """
        if page_object.job_ids:
            job_id_list = page_object.job_ids.split(',')
            for job_id in job_id_list:
                job_info = await cls.job_detail_services(int(job_id))
                await JobDao.delete_job_dao(JobModel(jobId=job_id))
                await SchedulerUtil.broadcast_scheduler_sync(app_scope=job_info.app_scope)
            return CrudResponseModel(is_success=True, message='删除成功')
        raise ServiceException(message='传入定时任务id为空')

    @classmethod
    async def job_detail_services(cls, job_id: int) -> JobModel:
        """
        获取定时任务详细信息service

        :param job_id: 定时任务id
        :return: 定时任务id对应的信息
        """
        job = await JobDao.get_job_detail_by_id(job_id=job_id)
        result = JobModel(**CamelCaseUtil.transform_result(job)) if job else JobModel()

        return result

    @staticmethod
    async def export_job_list_services(request: Request, job_list: list) -> bytes:
        """
        导出定时任务信息service

        :param request: Request对象
        :param job_list: 定时任务信息列表
        :return: 定时任务信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'jobId': '任务编码',
            'jobName': '任务名称',
            'jobGroup': '任务组名',
            'jobExecutor': '任务执行器',
            'invokeTarget': '调用目标字符串',
            'jobArgs': '位置参数',
            'jobKwargs': '关键字参数',
            'cronExpression': 'cron执行表达式',
            'misfirePolicy': '计划执行错误策略',
            'concurrent': '是否并发执行',
            'status': '状态',
            'appScope': '所属应用',
            'createBy': '创建者',
            'createTime': '创建时间',
            'updateBy': '更新者',
            'updateTime': '更新时间',
            'remark': '备注',
        }

        job_group_list = await DictDataService.query_dict_data_list_from_cache_services(
            request.app.state.redis, dict_type='sys_job_group'
        )
        job_group_option = [{'label': item.get('dictLabel'), 'value': item.get('dictValue')} for item in job_group_list]
        job_group_option_dict = {item.get('value'): item for item in job_group_option}
        job_executor_list = await DictDataService.query_dict_data_list_from_cache_services(
            request.app.state.redis, dict_type='sys_job_executor'
        )
        job_executor_option = [
            {'label': item.get('dictLabel'), 'value': item.get('dictValue')} for item in job_executor_list
        ]
        job_executor_option_dict = {item.get('value'): item for item in job_executor_option}

        for item in job_list:
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '暂停'
            if str(item.get('jobGroup')) in job_group_option_dict:
                item['jobGroup'] = job_group_option_dict.get(str(item.get('jobGroup'))).get('label')
            if str(item.get('jobExecutor')) in job_executor_option_dict:
                item['jobExecutor'] = job_executor_option_dict.get(str(item.get('jobExecutor'))).get('label')
            if item.get('misfirePolicy') == '1':
                item['misfirePolicy'] = '立即执行'
            elif item.get('misfirePolicy') == '2':
                item['misfirePolicy'] = '执行一次'
            else:
                item['misfirePolicy'] = '放弃执行'
            if item.get('concurrent') == '0':
                item['concurrent'] = '允许'
            else:
                item['concurrent'] = '禁止'
        binary_data = ExcelUtil.export_list2excel(job_list, mapping_dict)

        return binary_data
