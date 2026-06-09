# fix-config-loading-path

修复 common 组件配置文件路径问题：本地启动时，knowledge-common 中的 env.py 依赖 os.getcwd() 查找 .env 文件，导致从不同目录启动时找不到各子项目独立的配置文件。需要让配置加载逻辑从 knowledge_common 包位置回溯 workspace 根目录，自动在各子项目 src/configs/ 中查找对应的 .env 文件，且不依赖当前工作目录。
