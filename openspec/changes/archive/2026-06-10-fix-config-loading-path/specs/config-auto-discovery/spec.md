## ADDED Requirements

### Requirement: 配置加载不依赖当前工作目录
配置加载逻辑 SHALL 基于 `knowledge_common` 包的实际安装位置回溯 workspace 根目录，并在多个候选路径中自动查找 `.env` 配置文件，不依赖 `os.getcwd()` 作为唯一查找基准。

#### Scenario: 从 workspace 根目录启动子项目
- **WHEN** 开发者在 workspace 根目录执行 `uv run --package knowledge-admin python -m knowledge_admin.main`
- **THEN** 系统 SHALL 自动找到 `knowledge-admin/src/configs/.env.dev` 并加载其中的配置

#### Scenario: 从子项目目录启动
- **WHEN** 开发者在 `knowledge-admin/` 目录下执行启动命令
- **THEN** 系统 SHALL 优先检查 `knowledge-admin/src/configs/.env.dev`（向后兼容）

#### Scenario: Docker 环境无 .env 文件
- **WHEN** 在 Docker 容器中启动且不存在任何 `.env` 文件
- **THEN** 系统 SHALL 静默跳过文件加载，使用 pydantic-settings 默认值和已有的环境变量

### Requirement: 多候选路径优先级加载
系统 SHALL 按固定优先级顺序检查候选路径，第一个存在的 `.env` 文件即被加载，后续路径不再检查。

#### Scenario: 优先级验证
- **WHEN** 配置加载被触发
- **THEN** 系统 SHALL 按以下顺序查找（第一个命中即停止）：
  1. `cwd/configs/.env.{env}`
  2. `cwd/.env.{env}`
  3. workspace 根目录下各子项目的 `src/configs/.env.{env}`（按目录名排序遍历）

### Requirement: 加载结果可观测
系统 SHALL 在加载配置文件时打印日志，明确输出实际加载的文件路径或加载失败的原因。

#### Scenario: 成功加载
- **WHEN** 配置文件被成功找到并加载
- **THEN** 系统 SHALL 打印形如 `加载配置文件: /path/to/.env.dev` 的日志

#### Scenario: 未找到配置
- **WHEN** 所有候选路径都不存在配置文件
- **THEN** 系统 SHALL 打印警告日志 `警告: 未找到 .env.{env} 配置文件，使用默认配置`
