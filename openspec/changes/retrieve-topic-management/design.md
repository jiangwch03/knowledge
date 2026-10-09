## Context

问答主题闸门 `TopicGateService` 从字典 `rag_retrieve_topic` 读取「Milvus技术」等标签，交给模型判断相关后才走混合检索。问句不出现这些标签时，领域问题会被判成无关，检索不执行。

切分结果已在 `knowledge_document_segment`：超长节有父块（`skip_embedding=1`，全文）和子块；未超长的节只有一块，没有父块。混合检索的关键词通道是 Milvus 对整段 `text` 做 `standard` 分析后生成的 BM25 稀疏向量，库里没有一份可维护的关键词清单。

主题管理要单独建表，在用户保存主题时抽词。向量化流水线保持 `PENDING → CHUNKING → EMBEDDING → COMPLETED`。

## Goals / Non-Goals

**Goals:**

- 知识管理下提供主题的增删改查，名称唯一，删除为软删除。
- 用已完成的切分任务和 `jieba.analyse.extract_tags` 生成主题关键词，个数不超过用户选择的上限。
- 修改时名称不变；切分任务可换；旧关键词清理或保留由用户选择。
- 路由先用 jieba 对问句切词并与关键词表匹配，命中则直接走知识库检索；未命中再用主题名称走现有主题模型。

**Non-Goals:**

- 不把抽词插入向量化状态机，不改切分规则。
- 不修改 Milvus collection 的 `standard` 分析器，不把关键词写入稀疏向量。
- 不把关键词写进 `sys_dict_data`。
- 不自写 TF-IDF 或 BM25 抽词。

## Decisions

### 1. 表放在与 `knowledge_*` 相同的库，由 content 写入，retrieval 只读

主题和关键词要给管理页和每轮路由用。分段在 content，路由在 retrieval，两边已共用同一 MySQL。管理接口放在 `knowledge-content`，与 Embedding 任务接口一样由前端直连。retrieval 用只读映射读这两张表，沿用 `document_segment_ro` 的做法，避免每轮问答再发一次 RPC。

备选：字典继续存主题名，关键词另表。字典没有任务、上限和关键词，管理页还是要新表，字典会变成第二份名称来源。

备选：关键词接口走 Feign。路由在热路径上，多一次 HTTP 没有必要。

### 2. 两张表

`knowledge_retrieve_topic`：`topic_id`、`topic_name`（64）、`task_id`、`doc_id`、`keyword_limit`、`keyword_count`，以及 `user_id`、`dept_id`、审计字段、`del_flag`。

`knowledge_retrieve_topic_keyword`：`keyword_id`、`topic_id`、`keyword`（128）、`weight`、`del_flag`、时间字段。

名称唯一只约束 `del_flag='0'` 的行，在服务层校验。软删除后的名称可以再次使用。同一条切分任务允许被多个主题选用。

### 3. 抽词输入是父块，否则是独立块

只接受状态为 `COMPLETED` 且未删除的切分任务。取该任务下未删除分段：`skip_embedding=1` 的父块，以及 `parent_chunk_id` 为空的独立块。带 `parent_chunk_id` 的子块不参与，避免重叠正文被算两遍。

每一块调用 `jieba.analyse.extract_tags`，参数为 `topK=关键词上限`、`withWeight=True`、`allowPOS=('n','nz','eng')`。停用词使用 jieba 自带列表，并追加「下一步」「示例」「限制」「用户」「操作步骤」。同一关键词保留较高权重，再按权重截到上限。抽词在线程里执行，不占事件循环；与主题保存同一个事务，抽不出词则整次保存失败。

备选：按子块拼接后再抽。父块已经是整节原文，拼接会把重叠重复计入词频。

### 4. 修改时的关键词合并

更新请求不接收主题名称。`keepKeywords=false` 时，旧关键词软删除，只写入本次抽取结果。`keepKeywords=true` 时，旧词与新词按关键词合并，同一词保留较高权重，再按新的上限截断，然后软删除旧行并写入合并后的集合。只改上限、任务不变时同样重抽再截断，保证库里的词数不超过新上限。

### 5. 路由先匹配关键词，再走主题模型

存在未删除主题时：

1. 用 jieba 切开问句（与抽词同一分词器）。词条与关键词表做大小写不敏感匹配。
2. 命中任一关键词：`prompt_profile=knowledge`，不再调用主题模型。
3. 未命中：把未删除主题的名称填进现有 `topic_gate` 提示词，仍由模型返回 `related`。

一张未删除主题都没有时，继续读字典 `rag_retrieve_topic`，避免功能上线后、管理员尚未建主题时路由空白。一旦建出主题，字典不再参与。

关键词不参与 Milvus BM25。混合检索仍然对整句问话用 `standard` 分析器打稀疏分。

### 6. 菜单与接口

菜单名「主题管理」，挂在知识管理目录下，组件 `knowledge/topic/index`。权限：`rag:topic:list`、`rag:topic:query`、`rag:topic:add`、`rag:topic:edit`、`rag:topic:remove`，并授给 `role_id=1`。

内容服务前缀 `/topic`：分页列表、详情（含关键词）、创建、修改、删除。列表展示主题名称、文档标题、切分任务、上限和当前词数。前端切分任务下拉只列 `COMPLETED` 任务。

跨层用 VO，不用裸 dict 传主题和关键词。

## Risks / Trade-offs

- [jieba 词典与 Milvus `standard` 分析器切词不一致] → 接受。关键词只决定放不放行；放行后的 BM25 仍由 Milvus 自己切问句，两边不必是同一份词表。
- [大任务抽词耗时] → 保存只写入 `GENERATING` 并投递 `topic.keyword.pending`，消费端抽完后改为 `READY` 或 `FAILED`。不进向量化状态机。路由只读 `READY`。
- [停用词仍可能漏掉套话] → 只追加一小份停用词到 jieba，不另写打分。
- [字典回退让空库行为与现在相同] → 建出第一个主题后字典失效。需要在升级说明里写明要先建主题。

## Migration Plan

1. 执行升级 SQL：建表、菜单、角色授权。
2. 部署 content（含 jieba）、retrieval、前端。
3. 在主题管理里为主题建记录并勾选已完成切分任务。建完之前，路由仍走字典。
4. 回滚：检索改回只读字典；新表可留着，不影响向量数据。

## Open Questions

无。关键词上限、父子块取舍、修改时是否保留旧词，均按产品决定写入规格。
