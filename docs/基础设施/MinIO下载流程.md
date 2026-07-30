# MinIO 下载流程

## 1. 分层架构总览

```
Controller 层
    ↓
Service 层 (MinioService / KnowledgeMinioService)
    ↓
基础设施层 (MinioClient 单例封装)
    ↓
MinIO SDK (minio-py 7.2.20)
    ↓
MinIO 服务端 (S3 API)
```

## 2. 各层职责

### 2.1 Controller 层

- `minio_controller.py` — 接收前端 HTTP 请求
- 调用 `MinioService.download_file(object_name)` 完成下载
- 禁止直接调用 `MinioClient`

### 2.2 Service 层

- `MinioService` — 通用 MinIO 业务服务（桶 = `minio-data`）
- `KnowledgeMinioService` — 知识库专用（桶 = `knowledge-data`），继承 `MinioService`
- `MilvusMinioService` — Milvus 专用（桶 = `milvus-data`），继承 `MinioService`
- 所有方法均为 `@classmethod`，`MinioClient` 全局单例共享

### 2.3 基础设施层

- `MinioClient` — 单例封装，全局共享一个 `minio.Minio` SDK 客户端实例
- 所有同步阻塞的 SDK 方法均通过 `asyncio.to_thread` 转入线程池执行，避免阻塞事件循环

## 3. 调用链

```python
# Controller
result = await MinioService.download_file(object_name)

# Service (MinioService.download_file)
download_dir = f'{UploadConfig.DOWNLOAD_PATH}/minio'
local_path = await cls._client.download_file(object_name, download_dir, cls._bucket)

# Infra (MinioClient.download_file)
# ① 幂等性检查：本地已存在则直接返回
# ② 创建目标目录（含子目录）
# ③ asyncio.to_thread → 线程池 → Minio SDK fget_object
local_path = target_dir / object_name      # download_dir + object_name
if local_path.exists():                    # 幂等返回
    return str(local_path)
local_path.parent.mkdir(parents=True)
await asyncio.to_thread(
    self._client.fget_object,              # ← 同步阻塞操作
    bucket, object_name, str(local_path),
)
```

## 4. fget_object 核心下载机制

MinIO SDK 源码 (`minio/api.py` 第 1070 行)：

```
fget_object
  │
  ├── stat_object()              → 获取对象元信息（etag 用于临时文件命名）
  │
  ├── get_object(preload_content=False)   → HTTP GET，流式响应
  │     │
  │     └── _execute("GET", ..., preload_content=False)
  │           │
  │           └── urllib3 PoolManager.urlopen()  → 不预加载响应体
  │
  ├── 写入临时文件 tmp_file_path = f"{file_path}.{etag}.part.minio"
  │
  ├── for data in response.stream(amt=1024 * 1024):  # 1MB 分块
  │       tmp_file.write(data)                       # 直接写磁盘
  │
  └── os.rename(tmp_file_path, file_path)   → 重命名为目标文件名
```

**关键特性：**

| 特性 | 说明 |
|------|------|
| **内存安全** | 每次只读 1MB 分块，写入磁盘后释放，不将整个文件加载到内存 |
| **临时文件保护** | 先写 `.part.minio` 再 rename，防止下载中断产生脏文件 |
| **幂等性** | 本地已存在同名文件时跳过下载，直接返回已有路径 |
| **子目录支持** | `object_name` 含 `/` 时自动创建本地目录结构 |
| **断点续传** | 否（需业务方自行实现 Range 请求重试） |

## 5. 异步化模型

```
协程 (async def)
    │
    ▼
await asyncio.to_thread(func, ...)
    │
    ▼
事件循环默认线程池 (ThreadPoolExecutor)
max_workers = min(32, os.cpu_count() + 4)  → 约 9~12 (M 系列 Mac)
    │
    ▼
urllib3 PoolManager.urlopen()  → 同步阻塞 HTTP 请求
```

- 每个下载请求在线程池中执行同步 HTTP 请求+流式写盘
- 事件循环不被阻塞，其他协程可继续调度
- 线程池可复用，无需业务代码管理线程生命周期

## 6. 配置项

| 配置字段 | 默认值 | 说明 |
|----------|--------|------|
| `minio_address` | `http://localhost:9000` | MinIO 服务地址 |
| `minio_access_key_id` | `jiangwch` | 访问密钥 ID |
| `minio_secret_access_key` | `jiangwch` | 秘密访问密钥 |
| `minio_bucket_name` | `minio-data` | 默认存储桶 |
| `knowledge_bucket_name` | `knowledge-data` | 知识库专用桶 |
| `milvus_bucket_name` | `milvus-data` | Milvus 专用桶 |
| `DOWNLOAD_PATH` | `vf_admin/download_path` | 下载本地根目录 |
| `minio_use_ssl` | `False` | 是否使用 HTTPS |

## 7. 数据流图

```
用户请求
  │
  ▼
Controller
  │  MinioService.download_file(object_name)
  ▼
Service
  │  KnowledgeMinioService.download_file(object_name)
  │  (_bucket = 'knowledge-data')
  ▼
MinioClient.download_file(object_name, download_dir, bucket)
  │
  ├─ 幂等检查: local_path.exists()? ──Yes──→ 直接返回
  │
  └─ No
      │
      ▼
  asyncio.to_thread(self._client.fget_object, ...)
      │
      ▼
  MinIO SDK 线程池
      │
      ├─ stat_object()  → 获取 etag
      ├─ get_object()   → HTTP GET (preload_content=False)
      │     │
      │     ▼
      │   urllib3 流式响应
      │
      ├─ for chunk in response.stream(1MB):
      │     tmp_file.write(chunk)     ← 磁盘写入
      │
      └─ os.rename(tmp → final)       ← 原子重命名
           │
           ▼
  返回 local_path (绝对路径)
      │
      ▼
  业务方使用本地文件
```
