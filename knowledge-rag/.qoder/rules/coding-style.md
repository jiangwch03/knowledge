---
trigger: always_on
alwaysApply: true
---
# 包目录约束

```
knowledge_rag/
├── main.py                 # 应用入口（禁止修改）
├── server/
│   └── server.py           # FastAPI 应用工厂、生命周期管理
├── controller/             # API 路由定义
├── service/                # 业务逻辑层
├── infra/                  # 外部系统交互封装
│   ├── grpc/
│   │   └── vo/             # gRPC 专属 VO（与 protobuf 对应）
│   └── mineru/
│       └── vo/             # mineru 专属 VO
├── mapper/
│   ├── dao/                # 数据访问对象（SQL/ORM/事务）
│   └── do/                 # 数据库实体模型（SQLAlchemy）
├── vo/                     # Controller 层 VO（Pydantic BaseModel）
├── enums/                  # 枚举定义
└── configs/                # 配置定义
```

## 通用原则

| 原则           | 约束                                             |
|:-------------|:-----------------------------------------------|
| **单一职责**     | 禁止路由、业务、数据访问混写                                 |
| **依赖方向**     | controller → service/infra → mapper/dao，禁止反向依赖 |
| **VO 隔离**    | `vo/` 仅用于 HTTP，`infra/*/vo/` 用于外部协议，禁止混用       |
| **最小暴露**     | `__init__.py` 仅暴露必要符号，内部实现以下划线开头               |
| **变量定义规则**   | 变量必须声明类型，非必要禁止使用any类型                          |
| **抽象封装解耦原则** | 每个层级的代码都要分析抽象封装解耦的可能性,要考虑代码可扩展性避免代码多次修改的可能性    |


## 基础设施使用

| 场景 | 要求 |
|:---|:---|
| 日志 | 强制使用 `knowledge_common.utils.log_util.logger` |
| 异常 | 统一抛出 `ServiceException` |

## Controller 层约束

- **权限校验**：默认必须添加 `dependencies=[UserInterfaceAuthDependency('权限标识')]`
- **统一返回**：`return ResponseUtil.success(data=xxx)`，`response_model` 指定为 `DataResponseModel` / `PageResponseModel` / `DynamicResponseModel`
- **数据权限**：使用 `DataScopeDependency` 注入动态 SQL
- **数据库操作**：使用 `DBSessionDependency` 注入 `AsyncSession`

> 示例：核心结构为 `dependencies=[UserInterfaceAuthDependency('...')]` + `response_model=DataResponseModel[...]` + `query_db: Annotated[AsyncSession, DBSessionDependency()]` + `return ResponseUtil.success(data=...)`
## Service / DAO 层事务约束

| 层级 | 要求 |
|:---|:---|
| **Service** | 方法接收 `query_db: AsyncSession`；统一提交/回滚；禁止直接操作数据库 |
| **DAO** | 方法接收 `db: AsyncSession`；涉及更新需 `await db.flush()` |

## 模块命名

- 小写 + 下划线分隔，以 `_包名` 结尾，如 `mineru_base_vo.py`
- `enums`、`configs` 包去 `s`，如 `mineru_enum.py`、`mineru_config.py`
