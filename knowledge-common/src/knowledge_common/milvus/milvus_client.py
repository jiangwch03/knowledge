from __future__ import annotations

import asyncio
import threading
from typing import Any, TypeVar

from pymilvus import MilvusClient

from knowledge_common.config.env import MilvusConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.milvus.vo.base import BaseMilvusVo, MilvusSearchHit

TVo = TypeVar('TVo', bound=BaseMilvusVo)


class KnowledgeMilvusClient:
    """Milvus 基座：共享连接 + 增删改查。

    - 连接按进程懒加载单例（uri/token/db 来自 ``MilvusConfig``）
    - 同步 pymilvus SDK，对外 async 通过 ``asyncio.to_thread`` 卸到线程池
    - ``collection`` 必传；写入/读取均使用 ``BaseMilvusVo`` 子类，不做 DDL
    - ``query`` / ``search`` 必传 ``vo_cls``，``output_fields`` 默认由其推导
    """

    _raw: MilvusClient | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._client()

    @classmethod
    def _client(cls) -> MilvusClient:
        """获取（或创建）进程内共享的 ``MilvusClient``。"""
        if cls._raw is None:
            with cls._lock:
                if cls._raw is None:
                    token = MilvusConfig.milvus_token or None
                    cls._raw = MilvusClient(
                        uri=MilvusConfig.milvus_uri,
                        token=token,
                        db_name=MilvusConfig.milvus_db,
                    )
        return cls._raw

    @staticmethod
    def _collection(name: str) -> str:
        """校验并规范化 collection 名。"""
        cleaned = (name or '').strip()
        if not cleaned:
            raise ServiceException('Milvus collection 未指定')
        return cleaned

    def _assert_exists(self, collection: str) -> None:
        """collection 不存在则抛错（写/读前兜底）。"""
        if not self._client().has_collection(collection):
            raise ServiceException(f'Milvus collection 不存在: {collection}')

    @staticmethod
    def _to_rows(rows: list[BaseMilvusVo]) -> list[dict[str, Any]]:
        return [row.to_row() for row in rows]

    # ── 校验 ──────────────────────────────────────────────

    async def validate_collection(
        self,
        collection: str,
        dimensions: int,
        *,
        vector_field: str = 'vector',
    ) -> None:
        """校验 collection 存在，且指定向量字段维度与 ``dimensions`` 一致。"""
        name = self._collection(collection)

        def _run() -> None:
            self._assert_exists(name)
            desc = self._client().describe_collection(name)
            for field in desc.get('fields', []):
                if field.get('name') != vector_field:
                    continue
                params = field.get('params') or field.get('type_params') or {}
                dim = params.get('dim')
                if dim is not None and int(dim) != dimensions:
                    raise ServiceException(
                        f'Milvus collection 维度 {dim} 与适配维度 {dimensions} 不一致'
                    )
                return
            raise ServiceException(f'Milvus collection 缺少向量字段: {name}.{vector_field}')

        await asyncio.to_thread(_run)

    # ── 增 ───────────────────────────────────────────────

    async def insert(self, collection: str, row: BaseMilvusVo) -> None:
        """增（单条）。"""
        await self.insert_batch(collection, [row])

    async def insert_batch(self, collection: str, rows: list[BaseMilvusVo]) -> None:
        """增（批量）；``rows`` 为空则 noop。"""
        name = self._collection(collection)
        payload = self._to_rows(rows)

        def _run() -> None:
            if payload:
                self._client().insert(collection_name=name, data=payload)

        await asyncio.to_thread(_run)

    # ── 改 ───────────────────────────────────────────────

    async def upsert(self, collection: str, row: BaseMilvusVo) -> None:
        """改（单条）：按主键 upsert。"""
        await self.upsert_batch(collection, [row])

    async def upsert_batch(self, collection: str, rows: list[BaseMilvusVo]) -> None:
        """改（批量）：按主键 upsert；``rows`` 为空则 noop。"""
        name = self._collection(collection)
        payload = self._to_rows(rows)

        def _run() -> None:
            if payload:
                self._client().upsert(collection_name=name, data=payload)

        await asyncio.to_thread(_run)

    async def partial_update_batch(self, collection: str, rows: list[BaseMilvusVo]) -> None:
        """按主键部分更新（Milvus ``partial_update=True``）。

        对每个 VO 调用 ``to_partial_row()``：只提交显式赋值且非 None 的字段，无需重传向量。
        """
        name = self._collection(collection)
        payload = [row.to_partial_row() for row in rows]
        if not payload:
            return

        def _run() -> None:
            self._assert_exists(name)
            self._client().upsert(collection_name=name, data=payload, partial_update=True)

        await asyncio.to_thread(_run)

    # ── 删 ───────────────────────────────────────────────

    async def delete_by_id(self, collection: str, entity_id: str | int) -> None:
        """删（单条）：按主键删除。"""
        await self.delete_by_ids(collection, [entity_id])

    async def delete_by_ids(self, collection: str, entity_ids: list[str | int]) -> None:
        """删（批量）：按主键列表删除；``entity_ids`` 为空则 noop。"""
        name = self._collection(collection)
        if not entity_ids:
            return

        def _run() -> None:
            self._assert_exists(name)
            self._client().delete(collection_name=name, ids=entity_ids)

        await asyncio.to_thread(_run)

    async def delete_by_filter(self, collection: str, filter_expr: str) -> None:
        """删：按标量 filter 删除，例如 ``task_id in [1, 2]``。"""
        name = self._collection(collection)
        if not filter_expr or not filter_expr.strip():
            raise ServiceException('Milvus delete 必须提供 filter 表达式')

        def _run() -> None:
            self._assert_exists(name)
            self._client().delete(collection_name=name, filter=filter_expr)

        await asyncio.to_thread(_run)

    # ── 查 ───────────────────────────────────────────────

    @staticmethod
    def _resolve_output_fields(
        vo_cls: type[BaseMilvusVo],
        output_fields: list[str] | None,
    ) -> list[str]:
        return output_fields if output_fields is not None else vo_cls.output_fields()

    @staticmethod
    def _hit_entity(hit: dict[str, Any]) -> dict[str, Any]:
        """兼容 entity 嵌套或扁平两种 search 返回形态。"""
        entity = hit.get('entity')
        if isinstance(entity, dict):
            return entity
        return {k: v for k, v in hit.items() if k not in {'id', 'distance', 'score'}}

    async def query(
        self,
        collection: str,
        filter_expr: str,
        vo_cls: type[TVo],
        *,
        output_fields: list[str] | None = None,
        limit: int = 10,
    ) -> list[TVo]:
        """查：标量过滤（非向量 ANN）；``output_fields`` 默认取自 ``vo_cls.output_fields()``。"""
        name = self._collection(collection)
        if not filter_expr or not filter_expr.strip():
            raise ServiceException('Milvus query 必须提供 filter 表达式')
        fields = self._resolve_output_fields(vo_cls, output_fields)

        def _run() -> list[dict[str, Any]]:
            self._assert_exists(name)
            return self._client().query(
                collection_name=name,
                filter=filter_expr,
                limit=limit,
                output_fields=fields,
            )

        rows = await asyncio.to_thread(_run)
        return [vo_cls.from_row(row) for row in rows]

    async def search(
        self,
        collection: str,
        vectors: list[list[float]],
        vo_cls: type[TVo],
        *,
        limit: int = 10,
        filter_expr: str = '',
        output_fields: list[str] | None = None,
        search_params: dict[str, Any] | None = None,
        anns_field: str = 'vector',
    ) -> list[list[MilvusSearchHit[TVo]]]:
        """查：向量相似度检索；``output_fields`` 默认取自 ``vo_cls.output_fields()``。"""
        name = self._collection(collection)
        if not vectors:
            return []
        fields = self._resolve_output_fields(vo_cls, output_fields)

        def _run() -> list[list[dict[str, Any]]]:
            self._assert_exists(name)
            return self._client().search(
                collection_name=name,
                data=vectors,
                filter=filter_expr or '',
                limit=limit,
                search_params=search_params or {'metric_type': 'COSINE'},
                anns_field=anns_field,
                output_fields=fields,
            )

        raw = await asyncio.to_thread(_run)
        result: list[list[MilvusSearchHit[TVo]]] = []
        for hits in raw:
            batch: list[MilvusSearchHit[TVo]] = []
            for hit in hits:
                batch.append(
                    MilvusSearchHit[TVo](
                        id=hit['id'],
                        distance=float(hit.get('distance', hit.get('score', 0.0))),
                        entity=vo_cls.from_row(self._hit_entity(hit)),
                    )
                )
            result.append(batch)
        return result
