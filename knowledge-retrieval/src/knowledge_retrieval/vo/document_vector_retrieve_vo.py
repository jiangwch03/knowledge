from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from knowledge_common.milvus import DocumentVectorVo, MilvusSearchHit
from knowledge_common.vo.base_vo import BaseVo
from knowledge_retrieval.enums.release_tag_enum import ReleaseTag


class DocumentVectorRetrieveRequestVo(BaseVo):
    """文档向量检索请求。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    query: str = Field(..., description='自然语言查询')
    top_k: int = Field(default=5, ge=1, le=50, description='返回条数，默认 5')
    score_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            '稠密向量 COSINE 范围检索下界（Milvus radius）；'
            '>0 时仅保留相似度高于该值的向量路候选，不作用于 RRF/精排分；默认 0.5；0 表示不限制'
        ),
    )
    release_tag: ReleaseTag = Field(
        default=ReleaseTag.PROD,
        description='发布标签过滤，默认 prod（canary/prod/pending_delete）',
    )
    task_id: int | None = Field(
        default=None,
        description='可选：按向量化任务 ID 过滤，仅用于调试 / RAGAS 评测，非生产流量路由',
    )
    expand_parent: bool = Field(default=True, description='子片命中时是否回填父片全文')
    enable_rerank: bool = Field(
        default=False,
        description='是否对 hybrid RRF 候选做语义精排（需配置 document_rerank；失败则沿用 RRF）',
    )
    rrf_k: int = Field(
        default=60,
        ge=1,
        description='RRFRanker 常数 k；越大则靠前名次权重衰减越缓；默认 60',
    )

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        text = (v or '').strip()
        if not text:
            raise ValueError('query 不能为空')
        return text


class DocumentVectorRetrieveHitVo(BaseModel):
    """检索业务命中（精排 / 父片回填 / 对外响应）；与 MilvusSearchHit 分离。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str = Field(..., description='Milvus 主键 embedding_id')
    score: float = Field(..., description='相关性分（RRF 或精排分，越大越相关）')
    doc_id: int | None = Field(default=None, description='文档 ID')
    file_id: int | None = Field(default=None, description='文件 ID')
    task_id: int | None = Field(default=None, description='向量化任务 ID')
    release_tag: str | None = Field(default=None, description='发布标签')
    doc_title: str | None = Field(default=None, description='文档标题')
    doc_version: str | None = Field(default=None, description='文档版本')
    text: str | None = Field(default=None, description='展示正文（父片回填后为父片全文）')
    chunk_id: str | None = Field(default=None, description='向量命中的分片 ID（Milvus 入库的子片/叶子片）')
    parent_chunk_id: str | None = Field(default=None, description='父分片 ID；无父则为空')
    dept_id: int | None = Field(default=None, description='所属部门 ID')
    user_id: int | None = Field(default=None, description='所属用户 ID')

    @classmethod
    def from_milvus_hit(cls, hit: MilvusSearchHit[DocumentVectorVo]) -> Self:
        """Milvus 原生命中 → 业务命中（仅在检索服务边界转换一次）。"""
        entity = hit.entity
        parent = (entity.parent_chunk_id or '').strip()
        return cls(
            id=str(hit.id),
            score=float(hit.distance),
            doc_id=entity.doc_id,
            file_id=entity.file_id,
            task_id=entity.task_id,
            release_tag=entity.release_tag,
            doc_title=entity.doc_title,
            doc_version=entity.doc_version,
            text=entity.text,
            chunk_id=entity.chunk_id or '',
            parent_chunk_id=parent or None,
            dept_id=entity.dept_id,
            user_id=entity.user_id,
        )


class DocumentVectorRetrieveResponseVo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    query: str = Field(..., description='实际用于检索的查询文本')
    hits: list[DocumentVectorRetrieveHitVo] = Field(
        default_factory=list,
        description='检索命中列表（按相关性降序）',
    )