## 1. 数据与依赖

- [x] 1.1 新增升级 SQL：`knowledge_retrieve_topic`、`knowledge_retrieve_topic_keyword`，菜单「主题管理」及 `rag:topic:*` 按钮权限，并授给 `role_id=1`
- [x] 1.2 在 `knowledge-content` 与 `knowledge-retrieval` 增加 `jieba` 依赖

## 2. 主题维护（knowledge-content）

- [x] 2.1 增加主题、关键词的 DO / DAO / VO，列表带出文档标题与词数
- [x] 2.2 实现抽词：已完成任务的父块与无父块分段，调用 `jieba.analyse.extract_tags`，合并权重后按上限截断
- [x] 2.3 实现创建、修改、软删除：名称唯一且修改时不可改名；修改时按用户选择清理或合并旧关键词
- [x] 2.4 暴露 `/topic` 的列表、详情、创建、修改、删除接口，并加上对应权限

## 3. 主题路由（knowledge-retrieval）

- [x] 3.1 增加主题表与关键词表的只读映射
- [x] 3.2 调整 `TopicGateService`：有主题时先做 jieba 关键词命中，未命中再用主题名称走主题模型；没有主题时仍读 `rag_retrieve_topic`

## 4. 管理页（knowledge-web）

- [x] 4.1 增加主题管理 API 与页面：新建（名称、已完成切分任务、关键词上限）、修改（名称只读，任务可改，清理或保留旧词）、删除、查看关键词

## 5. 验证

- [x] 5.1 为抽词截断、父子块选取、关键词命中路由补单元测试
- [ ] 5.2 在浏览器走通主题的新建、修改、删除，并确认未改向量化流水线
