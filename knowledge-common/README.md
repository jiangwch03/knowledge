# knowledge-common

跨服务公共基础库，由 `knowledge-admin` / `knowledge-content` / `knowledge-retrieval` 通过 uv workspace 引用。

设计原则：**通用归 common，业务归子项目**。换中间件才需要改的基础设施收敛于此，业务层只对接门面、装饰器与共享模型。

---

## 能力一览

| 能力域 | 模块 | 做什么 | 详细文档 |
|--------|------|--------|----------|
| 注解式事务 | `common/transactional.py` | `@transactional` / `@transactional_sync`，ContextVar Session，commit / rollback | [注解式事务管理](../docs/基础设施/注解式事务管理.md) |
| 请求上下文 | `common/context.py` 等 | 当前用户、Session、Redis、Trace 等请求级状态 | [启动流程与生命周期](../docs/系统架构/启动流程与生命周期.md) |
| 声明式注解 | `common/annotation/` | `@Log` 操作日志、`@Cache` 接口缓存、`@RateLimit` 限流 | [中间件链与注解切面](../docs/系统架构/中间件链与注解切面.md) |
| 鉴权切面 | `common/aspect/` | `pre_auth`（JWT）、`interface_auth`（接口权限）、`data_scope`（数据范围） | 同上 |
| 路由注册 | `common/router.py` | 按包路径自动发现并注册 FastAPI 路由 | [启动流程](../docs/系统架构/启动流程与生命周期.md) |
| 中间件链 | `middlewares/` | Trace、CORS、GZip、Session、Redis 上下文、传输加密、演示模式、响应头等 | [中间件链与注解切面](../docs/系统架构/中间件链与注解切面.md) |
| 配置与客户端 | `config/` | 环境配置、DB / Scheduler 注入、Prompt 配置 | [Redis 与数据库](../docs/基础设施/Redis与数据库基础设施.md) |
| Redis | `redis/` | 连接池、客户端、Key 约定、分布式锁、分布式信号量、底层 Pub/Sub | [Redis 与数据库](../docs/基础设施/Redis与数据库基础设施.md)、[分布式信号量](../docs/基础设施/分布式信号量.md) |
| 消息流 | `message_stream/` | Kafka 风格门面：`@consumer` + `produce`；Redis Stream / Kafka 可插拔 | [消息流服务](../docs/基础设施/消息流服务.md) |
| 广播 | `broadcast/` | `@subscriber` + `publish`；Redis Pub/Sub，用于调度同步等扇出通知 | [广播服务](../docs/基础设施/广播服务.md) |
| 内置消费者 / 订阅者 | `message/` | 日志聚合消费者、调度同步订阅者（各服务 lifespan 自动发现） | [日志聚合](../docs/基础设施/日志聚合.md)、[定时任务调度](../docs/基础设施/定时任务调度.md) |
| 定时任务 | `config/get_scheduler.py` 等 | APScheduler + Leader 选举；跨实例通过广播同步 | [定时任务调度](../docs/基础设施/定时任务调度.md) |
| 数据访问 | `mapper/` | 通用 `BaseDao`、共享表 DAO / DO（用户登录、字典、配置、日志、Job、AI 模型、Agent 会话等） | — |
| 视图模型 | `vo/` | 跨服务共享 VO（用户、角色、字典、Job、AI 模型、分页基类等） | — |
| 通用服务 | `service/` | 字典 / 配置缓存、登录用户、日志去重与落库、Job 日志、LLM Chat、文档 Embedding、RAG 配置等 | — |
| Agent 抽象 | `agent/` | LangGraph 通用构建块：状态、Schema、节点、短期记忆、流式 / SSE、会话服务 | — |
| 模型工厂 | `common/factory/` | LangChain / DashScope 等 LLM、Embedding 工厂 | — |
| Milvus | `milvus/` | 向量库客户端与行 / 检索 VO（写入与检索共用） | — |
| 跨服务 Facade | `facade/` | 跨进程调用相关接口 VO 约定 | — |
| 异常处理 | `exceptions/` | 统一业务异常与全局异常处理器 | — |
| 枚举 | `enums/`、`common/enums.py` | 删除标记、文档类型 / 来源、业务布尔标记等 | — |
| 子应用挂载 | `sub_applications/` | FastAPI 子应用 Mount | — |
| 工具集 | `utils/` | 加解密与传输加密、上传、分页、雪花 ID、Excel、Cron、IP、密码、响应封装等 | [MinIO 下载流程](../docs/基础设施/MinIO下载流程.md)（上传 / 对象相关） |

消息流 vs 广播（选型）：

| | 消息流 `MessageStreamService` | 广播 `BroadcastService` |
|--|------------------------------|-------------------------|
| 语义 | 可靠队列（消费组 + ack） | 扇出通知（可丢） |
| 接入 | `@consumer` + `produce` | `@subscriber` + `publish` |
| 典型场景 | 日志聚合、文档解析编排、长流程任务 | 定时任务跨实例同步、实时广播 |

---

## 目录结构

```
knowledge_common/
├── agent/            # Agent 通用抽象（state / schema / node / memory / runtime / stream）
├── broadcast/        # 广播门面与 Redis Pub/Sub 后端
├── common/           # 上下文、事务、注解、切面、路由、模型工厂
├── config/           # 环境与 DB / Scheduler / Prompt 配置
├── enums/            # 跨服务枚举
├── exceptions/       # 异常与全局处理
├── facade/           # 跨服务接口 VO
├── mapper/           # DAO / DO
├── message/          # 内置 consumer / subscriber
├── message_stream/   # 消息流门面与后端
├── middlewares/      # FastAPI 中间件
├── milvus/           # 向量库客户端与 VO
├── redis/            # Redis 连接、锁、信号量、Pub/Sub
├── service/          # 跨服务通用 Service
├── sub_applications/ # 子应用挂载
├── utils/            # 工具类
└── vo/               # 共享 VO
```

---

## 接入约定

各业务服务在 FastAPI lifespan 中统一拉起公共基础设施（顺序与细节见 [启动流程与生命周期](../docs/系统架构/启动流程与生命周期.md)）：

1. 初始化 DB / Redis / Scheduler 等客户端
2. `MessageStreamService`：`init` → 注册扫描路径 → `discover_and_start`
3. `BroadcastService`：同上
4. 关闭阶段对上述门面调用 `shutdown`

业务侧声明消费 / 订阅时用装饰器即可；框架负责扫描、拉起后台协程与 ack / 重连。日志聚合、调度同步等已在 `message/` 内维护，业务项目一般无需再写一份。

---

## 测试

```bash
# 项目根目录
make test-common
# 或
.venv/bin/pytest knowledge-common/tests -v
```

静态 / Mock 用例任意环境可跑；依赖真 Redis 的集成用例在未连通时自动 skip。
