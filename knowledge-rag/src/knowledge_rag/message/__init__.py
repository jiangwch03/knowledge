"""
knowledge-rag 消息流业务包

- consumer/: 业务侧 @consumer 装饰器声明的消费者(由 MessageStreamService 启动时扫描注册)
- test_publisher.py: 测试发送类(应用启动时调用一次,验证生产-消费链路)
"""
