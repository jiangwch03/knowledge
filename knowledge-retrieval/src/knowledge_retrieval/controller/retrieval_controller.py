from typing import Annotated

from fastapi import Request, Response

from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_retrieval.service.document_vector_retrieve_service import DocumentVectorRetrieveService
from knowledge_retrieval.vo.document_vector_retrieve_vo import DocumentVectorRetrieveRequestVo, DocumentVectorRetrieveResponseVo

retrieval_controller = APIRouterPro(
    prefix='/retrieval',
    order_num=1,
    tags=['RETRIEVAL-知识检索'],
    dependencies=[PreAuthDependency()],
)


@retrieval_controller.post(
    '/search',
    summary='混合检索',
    description=(
        'Milvus 原生 hybrid_search（稠密 ANN + BM25，服务端 RRF）；'
        'scoreThreshold 仅约束稠密 COSINE 范围；rrfK 默认 60；可选 enableRerank 走语义精排。'
        'releaseTag 默认 prod；taskId 可选，仅用于调试与 RAGAS 评测，不是流量百分比灰度。'
    ),
    response_model=DataResponseModel[DocumentVectorRetrieveResponseVo],
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:query')],
)
async def search(
    request: Request,
    body: DocumentVectorRetrieveRequestVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await DocumentVectorRetrieveService.hybrid_retrieve(body, current_user)
    return ResponseUtil.success(data=result)
