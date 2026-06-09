## Why

本地开发启动时，`knowledge-common` 组件中的 `env.py` 使用 `os.getcwd()` 作为基准路径查找 `.env` 配置文件。由于各子项目（`knowledge-admin`、`knowledge-rag`）的配置文件独立存放在各自目录的 `src/configs/` 下，而启动命令的执行目录不确定（可能在 workspace 根目录，也可能在子项目目录），导致经常无法正确加载配置文件，服务以默认配置启动或配置缺失。

## What Changes

- 修改 `knowledge-common/src/knowledge_common/config/env.py` 中的 `parse_cli_args()` 方法
- 放弃对 `os.getcwd()` 的单一依赖，改为基于 `knowledge_common` 包的实际安装位置回溯 workspace 根目录
- 在多个候选路径中智能搜索 `.env.{env}` 配置文件（按优先级：cwd 向后兼容路径 → 各子项目 `src/configs/`）
- 找不到配置文件时静默跳过，不抛异常（兼容 Docker 环境变量注入场景）
- 保留现有的 CLI 参数解析逻辑（`--env` 参数、`APP_ENV` 环境变量）

## Capabilities

### New Capabilities

- `config-auto-discovery`: 基于包位置回溯的跨子项目配置自动发现能力

### Modified Capabilities

（无——本次变更为纯实现层修复，不涉及 spec-level 行为变化）

## Impact

- **核心改动文件**: `knowledge-common/src/knowledge_common/config/env.py`
- **受影响模块**: 所有导入 `knowledge_common.config.env` 的子项目（`knowledge-admin`、`knowledge-rag`）
- **Docker 部署**: 无影响——Docker 通过环境变量注入配置，`.env` 文件找不到时会静默使用默认值，环境变量优先级更高
- **向后兼容**: 保留——优先检查 `cwd` 下的 `configs/` 和 `.env.dev`，兼容现有启动习惯
