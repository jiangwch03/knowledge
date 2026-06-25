from typing import Annotated

from fastapi import Depends, File, Form, Path, Query, Request, Response, UploadFile
from knowledge_common.common.annotation.log_annotation import Log
from knowledge_common.common.aspect.data_scope import DataScopeDependency
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import PreAuthDependency
from knowledge_common.common.enums import BusinessType
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_content.enums.document_upload_status_enum import DocumentUploadStatus
from knowledge_content.mapper.do.upload_task_do import KnowledgeUploadDocumentParseTask
from pydantic_validation_decorator import ValidateFields
from sqlalchemy import ColumnElement

from knowledge_content.service.document_upload_parse_service import DocumentUploadParseService
from knowledge_content.vo.document_upload_parse_vo import (
    DocumentStatusOption,
    GetNextVersionResponseModel,
    GetParseTaskDetailsResponseModel,
    GetParseTaskResponseModel,
    HandleParseDecisionModel,
    ListDocumentRecordsQueryModel,
    ListDocumentRecordsResponseModel,
    ParseTaskItemResponseModel,
    UploadDocumentModel,
    UploadDocumentResponseModel,
    upload_document_form,
)

document_upload_parse_controller = APIRouterPro(
    prefix='/document-parse', order_num=9, tags=['CONTENT-资料上传'], dependencies=[PreAuthDependency()]
)

# 状态值到中文标签的映射
_STATUS_LABELS = {
    DocumentUploadStatus.PENDING.value: '待申请上传链接',
    DocumentUploadStatus.LINK_FAILED.value: '申请上传链接失败',
    DocumentUploadStatus.WAITING_UPLOAD.value: '等待文件上传',
    DocumentUploadStatus.UPLOADING.value: '文件上传中',
    DocumentUploadStatus.PARSING.value: '解析中',
    DocumentUploadStatus.COMPLETED.value: '解析完成',
    DocumentUploadStatus.USER_DECISION.value: '待人工决策',
    DocumentUploadStatus.CONVERTED.value: '转换完成',
    DocumentUploadStatus.CONVERT_FAILED.value: '转换失败',
}


@document_upload_parse_controller.get(
    '/status-options',
    summary='获取文档状态选项',
    description='返回文档上传记录状态枚举列表，用于前端下拉框',
    response_model=DataResponseModel[list[DocumentStatusOption]],
)
async def get_status_options() -> Response:
    """返回文档状态枚举列表，前端可直接用于下拉框"""
    options = [
        DocumentStatusOption(value=status.value, label=_STATUS_LABELS.get(status.value, status.value))
        for status in DocumentUploadStatus
    ]
    return ResponseUtil.success(data=options)


@document_upload_parse_controller.get(
    '/next-version',
    summary='获取文档下一版本号',
    description='根据文档标题查询最新版本号并返回 +1（查不到返回 1.0），用于前端自动填充',
    response_model=DataResponseModel[GetNextVersionResponseModel],
)
async def get_next_version(
    request: Request,
    doc_title: Annotated[str, Query(description='文档标题')],
) -> Response:
    """根据文档标题返回下一版本号"""
    next_version = await DocumentUploadParseService.get_next_version(doc_title)
    return ResponseUtil.success(data=GetNextVersionResponseModel(
        doc_title=doc_title,
        doc_version=next_version,
    ))


@document_upload_parse_controller.post(
    '/upload',
    summary='上传文档',
    description='支持 MD 直接落库，PDF/DOCX/XLSX 创建 MinerU 解析任务',
    response_model=DataResponseModel[UploadDocumentResponseModel],
    dependencies=[UserInterfaceAuthDependency('rag:document:upload')],
)
@ValidateFields(validate_model='upload_document')
@Log(title='资料上传', business_type=BusinessType.INSERT)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File(description='上传文件')],
    upload_model: Annotated[UploadDocumentModel, Depends(upload_document_form)],
) -> Response:
    result = await DocumentUploadParseService.upload_document(file=file, upload_model=upload_model)
    logger.info(f'文档上传成功: task_id={result.task_id}')
    return ResponseUtil.success(data=result)


@document_upload_parse_controller.get(
    '/list',
    summary='文档上传记录列表',
    description='分页查询文档上传记录（按数据权限过滤）',
    response_model=PageResponseModel[ListDocumentRecordsResponseModel],
    dependencies=[UserInterfaceAuthDependency('rag:document:list')],
)
async def list_document_records(
    request: Request,
    query_object: Annotated[ListDocumentRecordsQueryModel, Query()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(KnowledgeUploadDocumentParseTask)],
) -> Response:
    result = await DocumentUploadParseService.list_records(query_object, data_scope_sql)
    return ResponseUtil.success(model_content=result)


@document_upload_parse_controller.get(
    '/parse-task/{parse_task_id}',
    summary='获取解析任务详情',
    description='返回解析任务状态与错误信息',
    response_model=DataResponseModel[GetParseTaskResponseModel],
    dependencies=[UserInterfaceAuthDependency('rag:document:parse-task:query')],
)
async def get_parse_task(
    request: Request,
    parse_task_id: Annotated[int, Path(description='解析任务ID')],
) -> Response:
    result = await DocumentUploadParseService.get_parse_task(parse_task_id)
    return ResponseUtil.success(data=result)


@document_upload_parse_controller.get(
    '/parse-task/{parse_task_id}/details',
    summary='获取解析任务分段明细',
    description='分页返回分段明细',
    response_model=DataResponseModel[list[GetParseTaskDetailsResponseModel]],
    dependencies=[UserInterfaceAuthDependency('rag:document:parse-task:details')],
)
async def get_parse_task_details(
    request: Request,
    parse_task_id: Annotated[int, Path(description='解析任务ID')],
) -> Response:
    result = await DocumentUploadParseService.get_parse_task_details(parse_task_id)
    return ResponseUtil.success(data=result)


@document_upload_parse_controller.get(
    '/{task_id}/parse-tasks',
    summary='获取上传任务下的所有解析任务',
    description='返回该上传任务关联的所有解析任务列表（按创建时间降序）',
    response_model=DataResponseModel[list[ParseTaskItemResponseModel]],
    dependencies=[UserInterfaceAuthDependency('rag:document:parse-task:query')],
)
async def get_parse_tasks(
    request: Request,
    task_id: Annotated[int, Path(description='上传任务ID')],
) -> Response:
    result = await DocumentUploadParseService.get_parse_tasks_by_record(task_id)
    return ResponseUtil.success(data=result)


@document_upload_parse_controller.delete(
    '/{task_id}',
    summary='删除上传任务',
    description='仅允许删除尚未生成 knowledge_document 的任务',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:document:remove')],
)
@Log(title='资料上传', business_type=BusinessType.DELETE)
async def delete_document_record(
    request: Request,
    task_id: Annotated[int, Path(description='上传任务ID')],
) -> Response:
    await DocumentUploadParseService.delete_record(task_id)
    logger.info(f'上传任务删除成功: task_id={task_id}')
    return ResponseUtil.success(msg='删除成功')

@document_upload_parse_controller.post(
    '/parse-task/{parse_task_id}/decision',
    summary='用户决策',
    description='支持重试或删除',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:document:parse-task:decision')],
)
@Log(title='资料上传', business_type=BusinessType.UPDATE)
async def handle_parse_decision(
    request: Request,
    parse_task_id: Annotated[int, Path(description='解析任务ID')],
    decision: HandleParseDecisionModel,
) -> Response:
    await DocumentUploadParseService.handle_parse_decision(parse_task_id, decision)
    return ResponseUtil.success(msg='操作成功')
