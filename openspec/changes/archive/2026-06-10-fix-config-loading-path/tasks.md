## 1. 实现配置自动发现逻辑

- [x] 1.1 在 `env.py` 中添加 `_resolve_workspace_root()` 函数，基于 `__file__` 回溯 workspace 根目录
- [x] 1.2 在 `env.py` 中添加 `_find_env_file()` 函数，按优先级遍历候选路径查找 `.env` 文件
- [x] 1.3 修改 `parse_cli_args()` 方法，使用 `_find_env_file()` 替代固定的 `load_dotenv(env_file)` 调用
- [x] 1.4 完善加载日志输出：成功时打印实际加载路径，失败时打印警告信息

## 2. 验证与测试

- [x] 2.1 从 workspace 根目录启动 `knowledge-admin`，验证能正确加载 `knowledge-admin/src/configs/.env.dev`
- [x] 2.2 从 workspace 根目录启动 `knowledge-content`，验证能正确加载 `knowledge-content/src/configs/.env.dev`
- [x] 2.3 从子项目目录启动，验证向后兼容（cwd 优先检查）
- [x] 2.4 临时移除 `.env` 文件，验证启动不报错、使用默认值
