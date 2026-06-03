---
trigger: always_on
alwaysApply: true
---
# 包目录约束规范

以下规范定义了 `src/knowledge_rag` 目录下各包的职责边界，**不同类型文件必须定义到相应的包中**，禁止跨层混放。

## 1. `knowledge_rag/` — 应用根包

**允许存放：**
- `main.py`：应用入口文件，负责调用 `uvicorn.run()` 启动服务 **禁止修改该文件**。
- `__init__.py`：根包初始化（保持空或仅暴露公共符号）。

---

## 2. `knowledge_rag/server/` — 服务启动层

**允许存放：**
- `server.py`：FastAPI 应用工厂函数 `create_app()`、生命周期管理 `lifespan`、后台任务启停逻辑。
- 与服务启动、生命周期钩子直接相关的工具函数。

---

## 3. `knowledge_rag/controller/` — 控制器层（API 路由）

**允许存放：**
- FastAPI 路由模块（`@router.get/post/...` 等端点定义）。
- 请求参数解析、响应封装、HTTP 状态码处理。
- 调用 Service 层或 Infra 层完成业务动作。

---

## 4. `knowledge_rag/infra/` — 基础设施层

**职责：** 封装与外部系统（gRPC、minu 等）的交互细节。

### 4.1 `infra/grpc/`
**允许存放：**
- gRPC 客户端初始化、通道管理、stub 调用封装。
- `vo/`：gRPC 专属的请求/响应值对象（与 protobuf 结构对应）。

### 4.2 `infra/minu/`
**允许存放：**
- minu 服务调用封装、客户端逻辑。
- `vo/`：minu 交互专用的值对象定义。

---

## 5. `knowledge_rag/mapper/` — 数据访问层

### 5.1 `mapper/dao/`
**允许存放：**
- 数据访问对象（DAO）：负责执行原生 SQL、ORM 查询、事务控制。
- 数据库连接池使用、查询构造器调用。

### 5.2 `mapper/do/`
**允许存放：**
- 数据对象（Data Object / ORM Entity）：与数据库表一一对应的模型类。
- SQLAlchemy `declarative_base()` 子类、字段定义。

---

## 6. `knowledge_rag/vo/` — 视图对象 / 值对象（Controller 层）

**允许存放：**
- Pydantic `BaseModel` 子类：API 的请求体（Request VO）、响应体（Response VO）。
- 数据校验规则、字段别名、示例值。

---

## 通用原则

| 原则 | 说明 |
|------|------|
| **单一职责** | 每个包只处理一类职责，禁止将路由、业务、数据访问写在同一文件。 |
| **依赖方向** | `controller` → `infra` / `service` → `mapper` → `mapper/do`，禁止下层依赖上层。 |
| **VO 隔离** | 不同层/不同协议的 VO 禁止混用：`controller/vo/` 用于 HTTP API，`infra/*/vo/` 用于外部协议。 |
| **最小暴露** | `__init__.py` 中仅暴露该包对外必要的符号，内部实现细节以下划线开头隐藏。 |

# 已经实现功能使用说明

## 日志打印
**强制使用 knowledge_common.utils.log_util.logger** 例如:logger.info('获取成功') 

## controller 层代码约束
- 接口权限校验,除非说明接口不需要权限校验，否则必须天剑权限校验依赖注入:dependencies=[UserInterfaceAuthDependency('monitor:cache:list')]
- 接口返回统一使用return ResponseUtil.success(data=XXX) (XXX为返回值)
- 指定返回值类型response_model 确保所有 API 返回结构一致，DataResponseModel(单数据)，PageResponseModel(分页返回数据)，DynamicResponseModel(动态模型)
- 数据权限动态sql注入,使用DataScopeDependency依赖注入
- 涉及到数据库表操作要使用DBSessionDependency依赖注入session对象，确保数据操作的正确性和一致性。
示例代码:
"""
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.common.vo import DataResponseModel, ResponseBaseModel, DynamicResponseModel, PageResponseModel, PageModel
from knowledge_common.common.aspect.data_scope import DataScopeDependency
from knowledge_common.common.aspect.db_seesion import DBSessionDependency
@cache_controller.get(
    '/getNames',
    summary='获取缓存名称列表接口',
    description='用于获取缓存名称列表',
    response_model=DataResponseModel[list[CacheInfoModel]],
    dependencies=[UserInterfaceAuthDependency('monitor:cache:list')],
    query_db: Annotated[AsyncSession, DBSessionDependency()]
    user_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
    dept_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
  )
  async def get_monitor_cache_name(request: Request) -> Response:
      # 获取全量数据
      cache_name_list_result = await CacheService.get_cache_monitor_cache_name_services()
      logger.info('获取成功')

      return ResponseUtil.success(data=cache_name_list_result)
  """
# service 层代码约束
## 事物约束
- 服务层方法上添加参数 query_db: AsyncSession用来接收controller层传输的session对象
- 服务层必须进行统一的事物提交和异常回滚操作，确保数据操作的正确性和一致性。具体的数据库操作使用DAO层，禁止在Service层进行数据库操作。

# mapper.dao 层代码约束
## 事物约束
- dao层方法上添加参数 db: AsyncSession用来接收service层传输的session对象
- dao执行数据库sql涉及到表数据更新要及时调用await db.flush()，确保数据操作的正确性和一致性。

