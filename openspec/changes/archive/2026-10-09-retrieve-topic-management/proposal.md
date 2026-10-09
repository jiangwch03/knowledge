## Why

问答路由的主题现在写在字典 `rag_retrieve_topic` 里，只有「Milvus技术」这类名字。问句没出现这些名字时，主题模型会把领域问题判成无关，检索根本不会跑。主题和关键词需要能在知识管理里维护，并在路由阶段先做关键词命中。

## What Changes

- 在知识管理下增加菜单「主题管理」，对主题做增删改查。
- 新建主题：名称必填且在未删除主题中唯一；勾选一个已完成的切分任务；关键词上限只能是 30、50、100、150、200。保存时用 `jieba.analyse.extract_tags` 从该任务抽词，有父块用父块全文，没有父块用该块本身，去重后按权重截到上限。
- 修改主题：名称不可改；切分任务和关键词上限可改；旧关键词清理还是保留由用户选择。清理则按新任务重抽；保留则与新抽结果合并后再按上限截断。
- 删除主题：主题与其关键词一并软删除。
- 新增主题表、主题关键词表。抽词是用户保存主题时触发，不插入向量化流水线，不阻塞切分和入库。
- **BREAKING** 主题路由不再读字典 `rag_retrieve_topic`。问句用 jieba 切开，命中任一未删除主题的关键词则直接走知识库检索；未命中再用主题名称交给现有主题模型判断。
- 不改 Milvus 的 `standard` 分析器和 BM25 稀疏向量。关键词表只服务路由，不写入向量库。

## Capabilities

### New Capabilities

- `retrieve-topic-management`: 主题与关键词的维护、从切分任务抽词、上限与软删除。

### Modified Capabilities

- `knowledge-qa-agent`: 主题来源从系统字典改为主题表；路由先做关键词命中，未命中再走主题模型。

## Impact

- **服务**：`knowledge-content`（主题接口、抽词、分段读取）、`knowledge-retrieval`（主题路由改为读主题表）、`knowledge-web`（主题管理页）。
- **数据**：新增主题表与主题关键词表，与现有 `knowledge_*` 同库。菜单与 admin 角色授权写入升级 SQL。
- **依赖**：`jieba`（抽词与问句切词）。`jieba.analyse.extract_tags` 负责选词，不自写 TF-IDF。
- **不变**：向量化状态机、Milvus collection 分析器、混合检索的 BM25 通道。
