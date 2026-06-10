"""
消息流后端实现

- base.py:StreamBackend 抽象接口
- redis_stream.py:RedisStreamBackend(基于 redis.asyncio)
- kafka_stream.py:KafkaStreamBackend(基于 confluent-kafka-python + aio 异步包装)
- factory.py:create_backend(settings, redis) 后端工厂
"""
