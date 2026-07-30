<h1 align="center">
    <img alt="logo" src="./logo.png" width="120">
</h1>
<h1 align="center" style="margin: 30px 0 30px; font-weight: bold;">knowledge</h1>
<h4 align="center">企业知识库 RAG 系统 · 基于 RuoYi-Vue3-FastAPI 二次开发</h4>
<p align="center">
    <a href="https://github.com/jiangwch03/knowledge">
        <img alt="Github" src="https://img.shields.io/github/stars/jiangwch03/knowledge?style=social">
    </a>
    <a href="https://github.com/jiangwch03/knowledge">
        <img alt="project version" src="https://img.shields.io/badge/version-1.0.0-brightgreen.svg">
    </a>
    <a href="./LICENSE">
        <img alt="LICENSE" src="https://img.shields.io/badge/license-MIT-blue.svg">
    </a>
    <img alt="node version" src="https://img.shields.io/badge/node-≥18-blue">
    <img alt="python version" src="https://img.shields.io/badge/python-≥3.13-blue">
    <img alt="mysql version" src="https://img.shields.io/badge/MySQL-≥5.7-blue">
    <img alt="redis version" src="https://img.shields.io/badge/redis-≥6.2-blue">
    <img alt="milvus version" src="https://img.shields.io/badge/Milvus-≥2.6-blue">
    <img alt="langchain version" src="https://img.shields.io/badge/LangChain-1.3-blue">
    <img alt="langgraph version" src="https://img.shields.io/badge/LangGraph-1.2-blue">
    <img alt="deepagents version" src="https://img.shields.io/badge/DeepAgents-0.4-blue">
    <img alt="crawl4ai version" src="https://img.shields.io/badge/Crawl4AI-0.9-blue">
</p>

## 平台简介

knowledge 是一套企业知识库 RAG 系统，基于 [RuoYi-Vue3-FastAPI](https://github.com/insistence/RuoYi-Vue3-FastAPI) 二次开发，面向个人及企业开源使用。

* 前端采用 Vue3、Element Plus，基于若依前端改造，提供后台管理与知识业务界面。
* 后端采用 FastAPI、SQLAlchemy，按职责拆分为 `knowledge-admin`（后台管理）、`knowledge-content`（文档入库）、`knowledge-retrieval`（检索问答）三个服务，公共能力下沉至 `knowledge-common`。
* 数据层使用 MySQL、Redis、MinIO、Milvus；权限认证沿用 OAuth2 & Jwt，支持动态权限菜单与数据范围控制。
* 文档入库支持上传解析（MinerU）、切分向量化、网页爬取（Crawl4AI）；检索问答基于 LangChain / LangGraph / DeepAgents，支持混合检索与流式对话。
* Python 包由 uv workspace 统一管理（`requires-python >= 3.13`）；不提供若依 uni-app 移动端。
* 特别鸣谢：[RuoYi-Vue3-FastAPI](https://github.com/insistence/RuoYi-Vue3-FastAPI)、[RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3)

## 功能点对照（相对若依）

### 若依原有功能点

以下仍按原样保留：

1. 用户管理：用户是系统操作者，该功能主要完成系统用户配置。
2. 角色管理：角色菜单权限分配、设置角色按机构进行数据范围权限划分。
3. 菜单管理：配置系统菜单，操作权限，按钮权限标识等。
4. 部门管理：配置系统组织机构（公司、部门、小组）。
5. 岗位管理：配置系统用户所属担任职务。
6. 字典管理：对系统中经常使用的一些较为固定的数据进行维护。
7. 参数管理：对系统动态配置常用参数。
8. 通知公告：系统通知公告信息发布维护。
9. 操作日志：系统正常操作日志记录和查询；系统异常信息日志记录和查询。
10. 登录日志：系统登录日志记录查询包含登录异常。
11. 在线用户：当前系统中活跃用户状态监控。
12. 缓存监控：对系统的缓存信息查询，命令统计等。
13. 传输加密：支持前后端请求加密、响应解密、公钥轮换、运行策略下发与监控统计。

### 弃用若依功能点

1. 服务监控：已移除服务监控、数据监控相关菜单与页面。
2. 在线构建器：已移除表单拖拽构建器页面。
3. 代码生成：已移除代码生成菜单与一键生成下载能力。
4. AI对话：已移除管理端内置 AI 对话页（问答改由「知识问答」承接）。
5. 移动端：不提供若依 uni-app 移动端。

### 改造功能点

1. AI管理：保留「模型管理」；去掉原「AI对话」；新增「模型适配」，为业务功能点（如文档向量化、网页爬取、知识问答）绑定所用模型。
2. 系统接口：仍可查看接口文档；随后台拆分为多个服务，文档入口按服务分别提供。
3. 定时任务：界面增删改查与调度日志保留；任务按所属应用区分（管理后台 / 知识内容等）。

### 新增功能点

1. 资料上传：上传知识文档，查看解析状态，支持预览、下载与删除。
2. 网页爬虫：通过对话配置网页爬取，管理爬取会话、任务与入库文档。  
   > **说明**：当前实现距离「理想的动态适配爬取参数」还有一定距离，后续迭代优化。
3. Embedding 任务：对已入库文档发起切分与向量化，支持任务查询、创建、重试、删除与发布。
4. 知识问答：基于知识库进行会话式问答（含会话管理与流式回答）。

## 演示图

完整演示图见 [docs/演示图.md](./docs/演示图/演示图.md)。

- **若依原有模块**：外联上游截图（见 [README-RuoYi.md · 演示图](./README-RuoYi.md#演示图)），仅收录本项目仍使用的界面。
- **本项目新增 / 改造模块**：模型管理、模型适配、资料上传、网页爬虫、Embedding 任务、知识问答。

## 仓库结构

| 包 / 目录 | 职责 | 默认端口 |
|-----------|------|----------|
| `knowledge-common` | 公共基础设施（事务、消息流、广播、中间件、DAO 等） | — |
| `knowledge-admin` | 后台管理（用户 / 角色 / 菜单 / 字典 / 定时任务 / AI 模型） | `9099` |
| `knowledge-content` | 知识内容（文档上传、MinerU 解析、切分向量化、网页爬取） | `9098` |
| `knowledge-retrieval` | 知识检索与问答（混合检索、QA Agent） | `9101` |
| `knowledge-web` | Vue3 + Element Plus 前端 | Vite `:80` |
| `sql/` | MySQL 初始化与升级脚本；`milvus/` 为向量库脚本 | — |
| `docs/` | 架构与业务设计文档 | — |

Python 包由根目录 [uv workspace](./pyproject.toml) 管理（`requires-python >= 3.13`）。前端通过 `/dev-api`、`/dev-content-api`、`/dev-retrieval-api` 分别代理到上述三个后端。

## 快速开始

启动前请自行安装并启动以下外部依赖（本仓库不附带一键编排）：

| 依赖 | 用途 | 说明 |
|------|------|------|
| MySQL | 业务库 | ≥ 5.7；初始化脚本见 `sql/README.md` |
| Redis Stack | 缓存 / 会话 / 消息流等 | ≥ 6.2；需 Redis Stack（含 RedisJSON 等模块） |
| MinIO | 对象存储 | 文档与解析产物等 |
| Milvus | 向量库 | ≥ 2.6；集合脚本见 `sql/milvus/` |

连接地址与账号请按各服务 `configs/.env.*` 自行配置。

文档解析与知识问答还需自行配置：**MinerU Token**（`knowledge-content` 的 `.env`）、以及 **LLM / Embedding 模型 API**（后台「AI 管理 / 模型适配」）。Crawl4AI 默认 `sdk` 进程内调用，无需单独起服务；消息流默认 Redis Stream，无需 Kafka。

```bash
# 依赖（本地无 Nexus 时改用 PyPI）
uv sync --default-index pypi

# 数据库：按 sql/README.md 顺序执行 01 → 02 → 03

# 后端
uv run --package knowledge-admin python -m knowledge_admin.main
uv run --package knowledge-content python -m knowledge_content.main
uv run --package knowledge-retrieval python -m knowledge_retrieval.main

# 前端
cd knowledge-web && npm install && npm run dev
```

常用测试：`make help` / `make test-common` / `make test-all`。

## 文档

### 架构

| 主题 | 文档 |
|------|------|
| 系统架构总览 | [系统架构](./docs/系统架构/系统架构总览.md) |
| 应用启动与生命周期 | [启动流程](./docs/系统架构/启动流程与生命周期.md) |
| 中间件链与注解切面 | [中间件链](./docs/系统架构/中间件链与注解切面.md) |

### 基础设施

| 主题 | 文档 |
|------|------|
| 注解式事务管理 | [事务管理](./docs/基础设施/注解式事务管理.md) |
| 消息流服务（Kafka 风格） | [消息流](./docs/基础设施/消息流服务.md) |
| 广播服务（Redis Pub/Sub） | [广播服务](./docs/基础设施/广播服务.md) |
| Redis 与数据库 | [Redis 与数据库](./docs/基础设施/Redis与数据库基础设施.md) |
| 定时任务调度与同步 | [定时任务](./docs/基础设施/定时任务调度.md) |
| 日志聚合与操作日志落库 | [日志聚合](./docs/基础设施/日志聚合.md) |
| 分布式信号量 | [分布式信号量](./docs/基础设施/分布式信号量.md) |
| MinIO 下载流程 | [MinIO](./docs/基础设施/MinIO下载流程.md) |

### 业务（RAG）

主流程时序与状态流转（对齐当前代码）：

| 主题 | 文档 |
|------|------|
| 资料上传 | [资料上传流程](./docs/rag功能流程说明/资料上传流程.md) |
| 网页爬虫 | [网页爬虫流程](./docs/rag功能流程说明/网页爬虫流程.md) |
| 切分与向量化 | [切分与向量化流程](./docs/rag功能流程说明/切分与向量化流程.md) |
| 知识问答 | [知识问答流程](./docs/rag功能流程说明/知识问答流程.md) |
| SQL 脚本说明 | [sql/README.md](./sql/README.md) |
| 检索服务说明 | [knowledge-retrieval/README.md](./knowledge-retrieval/README.md) |

公共库能力说明见 [knowledge-common/README.md](./knowledge-common/README.md)。

## 许可证

本项目基于 [RuoYi-Vue3-FastAPI](https://github.com/insistence/RuoYi-Vue3-FastAPI) 开发，遵循 MIT License。详见 [LICENSE](./LICENSE)。
