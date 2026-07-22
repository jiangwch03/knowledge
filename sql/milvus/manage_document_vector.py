#!/usr/bin/env python3
"""
Milvus 初始化脚本：knowledge_document_vector
有则删除，再按 schema + 索引重建。

运行：
    python sql/milvus/manage_document_vector.py
    # 或：uv run --with 'pymilvus>=2.6.9' python sql/milvus/manage_document_vector.py
"""

from pymilvus import DataType, MilvusClient

# ─── 连接（按环境自行修改）───
MILVUS_URI = 'http://localhost:19530'
MILVUS_TOKEN = 'jiangwch:jiangwch'  # username:password，无鉴权填 ''
MILVUS_DB = 'knowledge_rag'
COLLECTION_NAME = 'knowledge_document_vector'
DIMENSIONS = 1024

# 1. 连接（先连默认库，确保 knowledge_rag 存在后再切入）
print(f'连接 Milvus: {MILVUS_URI}')
client = MilvusClient(uri=MILVUS_URI, token=MILVUS_TOKEN or None)
databases = client.list_databases()
if MILVUS_DB not in databases:
    print(f'创建数据库: {MILVUS_DB}')
    client.create_database(MILVUS_DB)
client.using_database(MILVUS_DB)
print(f'使用数据库: {MILVUS_DB}')

# 有则删除
if client.has_collection(COLLECTION_NAME):
    print(f'已存在，删除: {COLLECTION_NAME}')
    client.drop_collection(COLLECTION_NAME)

# 2. schema
schema = client.create_schema(
    auto_id=False,
    enable_dynamic_field=False,
    description='知识库文档向量（一期单一维度，与 document_embedding 适配 dimensions 一致）',
)
# 主键 id = MySQL knowledge_document_segment.embedding_id；chunk_id 为业务关联字段
schema.add_field(
    field_name='id',
    datatype=DataType.VARCHAR,
    is_primary=True,
    max_length=64,
    description='Milvus 主键（= knowledge_document_segment.embedding_id）',
)
schema.add_field(
    field_name='vector',
    datatype=DataType.FLOAT_VECTOR,
    dim=DIMENSIONS,
    description='embedding 稠密向量',
)
schema.add_field(field_name='doc_id', datatype=DataType.INT64, description='文档 ID（过滤/清理）')
schema.add_field(field_name='file_id', datatype=DataType.INT64, description='文件 ID')
schema.add_field(field_name='task_id', datatype=DataType.INT64, description='向量化任务 ID')
schema.add_field(
    field_name='release_tag',
    datatype=DataType.VARCHAR,
    max_length=32,
    description='发布标签：canary=灰度待验证，prod=正式检索流量，pending_delete=待异步清理',
)
schema.add_field(
    field_name='doc_title',
    datatype=DataType.VARCHAR,
    max_length=512,
    description='文档标题冗余',
)
schema.add_field(
    field_name='doc_version',
    datatype=DataType.VARCHAR,
    max_length=64,
    description='文档版本冗余',
)
schema.add_field(
    field_name='chunk_id',
    datatype=DataType.VARCHAR,
    max_length=64,
    description='业务分片 ID（对齐 knowledge_document_segment.chunk_id）',
)
schema.add_field(
    field_name='text',
    datatype=DataType.VARCHAR,
    max_length=65535,
    description='分片正文冗余',
)

# 3. 索引
# vector：向量索引 AUTOINDEX + COSINE（语义检索）
# 其余：标量倒排 INVERTED（按字段值过滤，如 release_tag==prod、task_id in [...]）
index_params = client.prepare_index_params()
index_params.add_index(
    field_name='vector',
    index_type='AUTOINDEX',
    metric_type='COSINE',
    index_name='idx_vector',
)
index_params.add_index(field_name='release_tag', index_type='INVERTED', index_name='idx_release_tag')
index_params.add_index(field_name='task_id', index_type='INVERTED', index_name='idx_task_id')
index_params.add_index(field_name='doc_id', index_type='INVERTED', index_name='idx_doc_id')
index_params.add_index(field_name='file_id', index_type='INVERTED', index_name='idx_file_id')
index_params.add_index(field_name='chunk_id', index_type='INVERTED', index_name='idx_chunk_id')

# 4. 创建 collection
print(f'创建 collection: {COLLECTION_NAME}, dim={DIMENSIONS}')
client.create_collection(
    collection_name=COLLECTION_NAME,
    schema=schema,
    index_params=index_params,
)
client.load_collection(COLLECTION_NAME)
print(f'完成: {COLLECTION_NAME}')
