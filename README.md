# knowledge
企业知识库RAG系统

## 许可证

本项目基于 [RuoYi-Vue3-FastAPI](https://github.com/insistence/RuoYi-Vue3-FastAPI) 开发，遵循 MIT License。
Copyright (c) 2024 insistence

## 项目代码梳理

### FastAPI Swagger UI 文档机制全景(RuoYi-Vue3-FastAPI已实现)
create_app() 针对 Swagger UI 的访问和构建做了自定义方案处理：

| 问题 | 解决方案 |
|------|---------|
| 国内无法加载默认 CDN 的 JS/CSS | Monkey-patch 替换静态资源地址 |
| FastAPI 内置路由受 root_path 影响，直连后端 404 | 注册独立的 /docs 路由 |
| 为什么 FastAPI 构造参数用 /proxy-docs 而不是 /docs | 避免 root_path 干扰 + 防止路由冲突 |

详细方案说明：[FastAPI Swagger UI 文档机制全景](./docs/ruoyi/fastapi-swagger-ui-overview.md)

### FastAPI 多进程
详细说明：[FastAPI 多进程](./docs/fastapi/fastapi-multiprocess.md)

### FastAPI 反向代理场景下的路由前缀处理
详细说明：[FastAPI 反向代理场景下的路由前缀处理](./docs/fastapi/fastapi-root-path-proxy.md)

## 基础组件改造说明

### 注解式事务管理
类 Spring `@Transactional` 的注解式事务装饰器，支持异步/同步双模式、7 种传播行为、嵌套事务统一提交/回滚，基于 `ContextVar` + `threading.local()` 实现上下文隔离。DAO 层通过 `get_current_session()` 统一获取 session，业务代码零侵入。
详细说明：[注解式事务管理机制](./docs/rag/annotated-transaction-management.md)

### 定时任务多项目运行支持优化说明
详细说明：[定时任务多项目运行支持优化说明](./docs/rag/job-app-scope-optimization.md)

### 定时任务调度同步机制
详细说明：[定时任务注册与同步调度机制](./docs/rag/scheduler-sync-flow.md)

### 消息流服务设计
把裸操作 Redis Stream 协议的耦合，变成「`@consumer` 声明 + `produce` 推送」的 Kafka 风格门面。`.env` 改 `MESSAGE_STREAM_BACKEND=redis|kafka` 即可切换后端，业务代码零行修改。
详细说明：[消息流服务设计](./docs/rag/message-stream-service-design.md)

### BroadcastService 广播服务
与 `MessageStreamService` 对等的广播抽象层。业务代码通过 `@subscriber` 装饰器声明消费者、`BroadcastService.publish()` 发布消息，完全隔离 Redis Pub/Sub 操作。Backend 采用单 pubsub 连接 + dispatch table 多路复用，支持自动重连和 handler 异常隔离。
详细说明：[BroadcastService 广播服务架构](./docs/rag/broadcast-service-abstraction.md)

### 日志聚合与操作日志落库机制
基于 `MessageStreamService` 框架实现的日志异步落库链路。推送侧用 `produce`，消费侧用 `@consumer` 装饰器，按 `app_name` 隔离，业务级去重由 `LogDedupHelper` 保证。
详细说明：[基于 MessageStreamService 的日志聚合流程](./docs/rag/log-aggregator-flow.md)



