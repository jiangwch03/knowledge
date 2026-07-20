from __future__ import annotations

from typing import Any, Generic, Mapping, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class BaseMilvusVo(BaseModel):
    """Milvus 行 VO 基类（对应一条 entity，类比 MySQL DO/VO）。

    业务侧按 collection schema 定义子类；写入时经 ``to_row()`` 交给 pymilvus。
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    def to_row(self) -> dict[str, Any]:
        """序列化为 Milvus insert/upsert 所需的字段字典。"""
        return self.model_dump()

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


class MilvusSearchHit(BaseModel, Generic[TMilvusVo]):
    """向量检索单条命中（``id`` / ``distance`` + 行 VO）。"""

    model_config = ConfigDict(extra='forbid')

    id: str | int
    distance: float
    entity: TMilvusVo = Field(..., description='命中行')
