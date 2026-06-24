## Context

当前项目的 `knowledge-common` 组件作为共享依赖包，承载了配置加载的核心逻辑（`env.py`）。各子项目（`knowledge-admin`、`knowledge-content`）的配置文件独立存放在各自目录的 `src/configs/.env.{env}` 中。

现有实现中，`parse_cli_args()` 使用 `load_dotenv('configs/.env.dev')` 加载配置，该调用隐式依赖 `os.getcwd()` 作为基准路径。由于本地开发时启动命令的执行目录不固定（可能从 workspace 根目录、子项目根目录或其他任意目录执行 `uv run`），导致 `.env` 文件经常找不到，服务以默认配置启动。

Docker 部署场景不受影响——配置通过环境变量注入，`.env` 文件的有无不影响最终配置值。

## Goals / Non-Goals

**Goals:**
- 本地开发时，无论从哪个目录启动，都能正确找到并加载对应子项目的 `.env` 配置文件
- 保持向后兼容：优先保留 cwd 查找逻辑，兼容现有启动习惯
- 配置加载失败时静默降级，不阻塞启动（兼容 Docker 环境变量注入场景）
- 仅修改 `env.py`，不改动各子项目的启动入口

**Non-Goals:**
- 不改动机密管理策略（`.env` 文件仍按现有方式管理）
- 不重构 pydantic-settings 的使用方式（`BaseSettings` 子类定义保持不变）
- 不引入新的配置格式或配置中心
- 不改写 CLI 参数解析逻辑（`--env`、`APP_ENV` 保留）

## Decisions

### 1. 基于包位置回溯 workspace 根目录

**决策**：从 `knowledge_common.config.env` 模块的 `__file__` 出发，向上回溯到 workspace 根目录，再从根目录遍历各子项目的 `src/configs/` 查找 `.env` 文件。

**理由**：
- `knowledge-common` 在 uv workspace 中以 editable install 方式安装，`__file__` 指向真实的源码路径，回溯可靠
- 不依赖 cwd，解决了"从任意目录启动"的核心问题
- 比 `inspect.stack()` 等运行时调用栈分析更简单、更稳定、性能更好

**替代方案**：
- `inspect.stack()` 回溯调用方 → 过度复杂，性能差，且调用方可能在 import chain 的任意位置
- 各子项目 `main.py` 预加载 `.env` → 需要改动多个文件，且 `server.py` 的 import 时机不可控
- 统一放到 workspace 根目录 → 破坏子项目配置独立性

### 2. 多候选路径优先级策略

**决策**：按以下优先级依次尝试，第一个存在的文件即被加载：

1. 从 `cwd` 向上回溯查找 `src/configs/.env.{env}` —— 覆盖从任意子目录启动的场景
2. workspace 根目录下各子项目的 `src/configs/.env.{env}`（按目录名排序）—— 覆盖从 workspace 根目录启动的场景

**理由**：
- 回溯逻辑覆盖从任意子目录启动的情况（如从 `knowledge-admin/`、`knowledge-content/src/knowledge_content/` 等）
- 第 2 步覆盖从 workspace 根目录启动的场景
- 去掉了 `cwd/.env` 等向后兼容路径，避免 cwd 下碰巧存在的 `.env` 文件被误加载
- 静默跳过（打印警告日志）而非抛异常，确保 Docker 场景不受影响

### 3. 不改动模块级实例化时机

**决策**：保留 `get_config = GetConfig()` 在模块导入时立即执行的现有行为。

**理由**：
- 改动实例化时机需要修改所有引用 `AppConfig` 等全局变量的代码，影响面过大
- 只要 `parse_cli_args()` 能正确找到 `.env` 文件，模块级实例化本身不是问题

## Risks / Trade-offs

- **[Risk]** 打包安装（wheel）后，`__file__` 指向 site-packages，回溯到的"workspace 根目录"可能不存在，导致第 3 步查找失效  
  → **Mitigation**: 第 3 步查找前检查目录是否存在；wheel 场景下 `.env` 文件本来就不会被打包，靠环境变量兜底，行为不变

- **[Risk]` 多个子项目同时存在同名的 `.env.dev` 文件时，查找顺序可能导致加载了非预期的配置  
  → **Mitigation**: 遍历顺序固定（按目录名排序），并在加载日志中打印实际加载的文件路径，便于排查

- **[Risk]** 去掉了 cwd 向后兼容路径，如果某些脚本或 CI 流程依赖在 cwd 下放 `.env` 文件，会失效  
  → **Mitigation**: 项目结构中不存在标准 `cwd/.env` 位置，所有配置均在 `src/configs/` 下；如有特殊需求可通过环境变量注入

## Migration Plan

无需迁移——本次变更为纯内部实现修复，对外接口（`AppConfig`、`DataBaseConfig` 等）和行为不变。开发者只需重新启动服务即可生效。

## Open Questions

（无）
