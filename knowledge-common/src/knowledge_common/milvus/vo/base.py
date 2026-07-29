from __future__ import annotations

from typing import Any, Generic, Mapping, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from knowledge_common.exceptions.exception import ServiceException


class BaseMilvusVo(BaseModel):
    """Milvus 行 VO 基类（对应一条 entity，类比 MySQL DO/VO）。

    业务侧按 collection schema 定义子类；写入时经 ``to_row()`` 交给 pymilvus。
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    def to_row(self) -> dict[str, Any]:
        """序列化为 Milvus insert/upsert 所需的字段字典（跳过 None）。"""
        data = self.model_dump(exclude_none=True)
        self._require_primary_key(data)
        return data

    def to_partial_row(self) -> dict[str, Any]:
        """部分更新：只序列化「显式赋值且非 None」的字段；须含主键 ``id``。"""
        data = self.model_dump(exclude_unset=True, exclude_none=True)
        self._require_primary_key(data)
        return data

    @staticmethod
    def _require_primary_key(data: dict[str, Any]) -> None:
        """校验主键 id 存在且有值（非空字符串 / 非 None）。"""
        if 'id' not in data:
            raise ServiceException('Milvus 写入必须设置主键 id')
        pk = data['id']
        if pk is None or (isinstance(pk, str) and not pk.strip()):
            raise ServiceException('Milvus 写入主键 id 不能为空')

    @classmethod
    def output_fields(cls, *, exclude: set[str] | None = None) -> list[str]:
        """供 query/search 的 ``output_fields``；默认排除 ``vector``（体积大且检索少用）。"""
        skip = exclude if exclude is not None else {'vector'}
        return [name for name in cls.model_fields if name not in skip]

    @classmethod
    def from_row(cls, data: Mapping[str, Any]) -> Self:
        """从 Milvus query/search 返回的 entity 反序列化。

        ``output_fields`` 默认不含 ``vector`` 时补空列表，避免必填校验失败。
        """
        payload = {name: data[name] for name in cls.model_fields if name in data}
        if 'vector' in cls.model_fields and 'vector' not in payload:
            payload['vector'] = []
        return cls.model_validate(payload)


TMilvusVo = TypeVar('TMilvusVo', bound=BaseMilvusVo)


class MilvusQueryRequestVo(BaseModel, Generic[TMilvusVo]):
    """Milvus ``query`` 请求参数（标量过滤，非向量 ANN）。"""

    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)

    collection: str = Field(..., description='collection 名')
    filter_expr: str = Field(..., description='标量过滤表达式')
    vo_cls: type[TMilvusVo] = Field(..., description='行 VO 类型（反序列化 + 默认 output_fields）')
    output_fields: list[str] | None = Field(default=None, description='输出字段；默认取自 vo_cls')
    limit: int = Field(default=10, ge=1, description='返回条数')


class MilvusSearchRequestVo(BaseModel, Generic[TMilvusVo]):
    """Milvus ``search`` 请求参数（稠密 ANN / BM25 稀疏共用）。"""

    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)

    collection: str = Field(..., description='collection 名')
    data: list[list[float]] | list[str] = Field(..., description='查询向量或 BM25 查询文本')
    vo_cls: type[TMilvusVo] = Field(..., description='行 VO 类型（反序列化 + 默认 output_fields）')
    limit: int = Field(default=10, ge=1, description='每路返回条数')
    filter_expr: str = Field(default='', description='标量过滤表达式')
    output_fields: list[str] | None = Field(default=None, description='输出字段；默认取自 vo_cls')
    search_params: dict[str, Any] | None = Field(
        default=None,
        description='检索参数；缺省 ``{"metric_type": "COSINE"}``',
    )
    anns_field: str = Field(default='vector', description='ANN 字段名（如 vector / sparse）')


class MilvusDenseChannelVo(BaseModel):
    """hybrid_search 稠密向量一路（对应 ``AnnSearchRequest``）。"""

    model_config = ConfigDict(extra='forbid')

    vector: list[float] = Field(..., description='稠密查询向量')
    anns_field: str = Field(default='vector', description='稠密向量字段')
    search_params: dict[str, Any] | None = Field(
        default=None,
        description='检索参数；缺省 ``{"metric_type": "COSINE"}``',
    )
    limit: int | None = Field(default=None, ge=1, description='本路召回条数；缺省用外层 limit')


class MilvusSparseChannelVo(BaseModel):
    """hybrid_search BM25 全文一路（对应 ``AnnSearchRequest``）。"""

    model_config = ConfigDict(extra='forbid')

    text: str = Field(..., description='BM25 查询原文（由 Milvus analyzer 分词）')
    anns_field: str = Field(default='sparse', description='BM25 稀疏字段')
    search_params: dict[str, Any] | None = Field(
        default=None,
        description='检索参数；缺省 ``{"metric_type": "BM25"}``',
    )
    limit: int | None = Field(default=None, ge=1, description='本路召回条数；缺省用外层 limit')


class MilvusHybridSearchRequestVo(BaseModel, Generic[TMilvusVo]):
    """Milvus ``hybrid_search``：dense ANN + sparse BM25，服务端 RRF 融合。"""

    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)

    collection: str = Field(..., description='collection 名')
    vo_cls: type[TMilvusVo] = Field(..., description='行 VO 类型（反序列化 + 默认 output_fields）')
    dense: MilvusDenseChannelVo = Field(..., description='稠密向量检索一路')
    sparse: MilvusSparseChannelVo = Field(..., description='BM25 全文检索一路')
    limit: int = Field(default=10, ge=1, description='融合后返回条数')
    filter_expr: str = Field(default='', description='两路共用的标量过滤表达式')
    output_fields: list[str] | None = Field(default=None, description='输出字段；默认取自 vo_cls')
    rrf_k: int = Field(default=60, ge=1, description='RRFRanker 常数 k')


class MilvusSearchHit(BaseModel, Generic[TMilvusVo]):
    """Milvus 检索单条命中（client 解析结果，仅含原生字段）。"""

    model_config = ConfigDict(extra='forbid')

    id: str | int = Field(..., description='命中主键')
    distance: float = Field(..., description='Milvus 返回分（ANN/BM25/RRF 等，语义随检索方式而定）')
    entity: TMilvusVo = Field(..., description='命中行 VO')
