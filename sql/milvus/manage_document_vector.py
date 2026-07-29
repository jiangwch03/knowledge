#!/usr/bin/env python3
"""
Milvus collection 创建脚本：knowledge_document_vector
有则删除，再按 schema + 索引重建。

字段要点：
- dept_id / user_id：向量侧 data_scope 过滤
- parent_chunk_id：子片指向父（检索侧可直接读，无需先查 MySQL）
- text + sparse + BM25 Function：混合检索关键词通道

注意：本脚本只负责 DDL 建库，会清空 collection。
存量数据需另行从 MySQL 回灌或重新向量化。

运行：
    python sql/milvus/manage_document_vector.py
    # 或：uv run --with 'pymilvus>=2.6.9' python sql/milvus/manage_document_vector.py
"""

from pymilvus import DataType, Function, FunctionType, MilvusClient

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
    description='知识库文档向量（稠密 ANN + BM25 全文；含 dept_id/user_id ACL）',
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
    field_name='parent_chunk_id',
    datatype=DataType.VARCHAR,
    max_length=64,
    description='父分片 ID（对齐 segment.parent_chunk_id；无父为空串）',
)
schema.add_field(
    field_name='text',
    datatype=DataType.VARCHAR,
    max_length=65535,
    enable_analyzer=True,
    analyzer_params={'type': 'standard'},
    description='分片正文冗余（BM25 输入）',
)
schema.add_field(
    field_name='dept_id',
    datatype=DataType.INT64,
    description='文档所属部门 ID（data_scope）',
)
schema.add_field(
    field_name='user_id',
    datatype=DataType.INT64,
    description='文档上传用户 ID（data_scope）',
)
schema.add_field(
    field_name='sparse',
    datatype=DataType.SPARSE_FLOAT_VECTOR,
    description='BM25 稀疏向量（由 Function 自动生成）',
)

bm25_function = Function(
    name='text_bm25',
    input_field_names=['text'],
    output_field_names=['sparse'],
    function_type=FunctionType.BM25,
)
schema.add_function(bm25_function)

# 3. 索引
index_params = client.prepare_index_params()
index_params.add_index(
    field_name='vector',
    index_type='AUTOINDEX',
    metric_type='COSINE',
    index_name='idx_vector',
)
index_params.add_index(
    field_name='sparse',
    index_type='SPARSE_INVERTED_INDEX',
    metric_type='BM25',
    index_name='idx_sparse_bm25',
)
index_params.add_index(field_name='release_tag', index_type='INVERTED', index_name='idx_release_tag')
index_params.add_index(field_name='task_id', index_type='INVERTED', index_name='idx_task_id')
index_params.add_index(field_name='doc_id', index_type='INVERTED', index_name='idx_doc_id')
index_params.add_index(field_name='file_id', index_type='INVERTED', index_name='idx_file_id')
index_params.add_index(field_name='chunk_id', index_type='INVERTED', index_name='idx_chunk_id')
index_params.add_index(field_name='parent_chunk_id', index_type='INVERTED', index_name='idx_parent_chunk_id')
index_params.add_index(field_name='dept_id', index_type='INVERTED', index_name='idx_dept_id')
index_params.add_index(field_name='user_id', index_type='INVERTED', index_name='idx_user_id')

# 4. 创建 collection
print(f'创建 collection: {COLLECTION_NAME}, dim={DIMENSIONS}')
client.create_collection(
    collection_name=COLLECTION_NAME,
    schema=schema,
    index_params=index_params,
)
client.load_collection(COLLECTION_NAME)
print(f'完成: {COLLECTION_NAME}')
