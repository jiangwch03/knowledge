"""
knowledge-admin 业务消费者包

每个 .py 文件内通过 @consumer(topic=..., group_id=...) 声明消费者函数,
MessageStreamService.discover_and_start() 启动时扫描本包,触发装饰器注册。

扫描路径在 knowledge_admin/server/server.py 的 lifespan 中通过
    MessageStreamService.register_consumer_paths(['knowledge_admin.message.consumer'])
显式注册。
"""
