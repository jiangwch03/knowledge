# SQL 执行说明

## 执行顺序

按文件名前缀序号 **从小到大** 依次执行。升级脚本均支持重复执行（幂等）。

| 序号 | 文件名 | 说明 | 操作类型 |
|------|--------|------|----------|
| 01 | `01_ruoyi-fastapi.sql` | 基础框架表（部门、用户、角色、菜单、字典、参数、定时任务、AI模型等） | DROP + CREATE + INSERT |
| 02 | `02_upgrade_knowledge_content.sql` | 知识内容业务（文档/上传/解析/Embedding/分段/爬取 Agent/模型适配/切分字典/菜单/调度；含 models.dev Profile 同步任务） | CREATE IF NOT EXISTS + INSERT(幂等) |
| 03 | `03_upgrade_knowledge_retrieval.sql` | 知识检索种子（主题字典、Tavily/精排参数、问答菜单权限、精排模型、QA Agent 适配） | INSERT(幂等) + UPDATE |
| 04 | `04_upgrade_proxy_pool_sync.sql` | 爬虫代理池拉取（30 秒，只增）+ 清理（1 分钟，只删）定时任务 | DELETE 旧单任务 + INSERT/UPDATE(幂等) |

## 依赖关系

```
01_ruoyi-fastapi
  └─► 02_upgrade_knowledge_content
        ├─► 03_upgrade_knowledge_retrieval
        └─► 04_upgrade_proxy_pool_sync
```

## 执行方式

### 新环境全量初始化

```bash
mysql -h <host> -P <port> -u <user> -p --default-character-set=utf8mb4 <database> < sql/01_ruoyi-fastapi.sql
mysql -h <host> -P <port> -u <user> -p --default-character-set=utf8mb4 <database> < sql/02_upgrade_knowledge_content.sql
mysql -h <host> -P <port> -u <user> -p --default-character-set=utf8mb4 <database> < sql/03_upgrade_knowledge_retrieval.sql
mysql -h <host> -P <port> -u <user> -p --default-character-set=utf8mb4 <database> < sql/04_upgrade_proxy_pool_sync.sql
```

### 增量升级

如果基础框架表已存在（01 已执行过），只需按序执行 02–04 中尚未执行的脚本即可。已发布环境仅需补跑 `04_upgrade_proxy_pool_sync.sql`。

## 注意事项

- `01_ruoyi-fastapi.sql` 使用 `DROP TABLE IF EXISTS` + `CREATE TABLE`，**会清空已有数据**，仅适用于全新环境初始化。
- 02、03、04 为幂等设计，可重复执行。
- 脚本中的 `api_key` 均为占位值（`sk-你自己的key`），部署后需在管理后台修改为真实 Key。
- 上下文窗口字段为 `max_input_tokens`，不再使用 `context_window`。
- 向量维度挂在 `knowledge_ai_model_function_adapter.dimensions`（业务适配），不挂 `ai_models`。
- `milvus/` 目录下为 Milvus 向量库相关脚本，与 MySQL 脚本独立执行。
