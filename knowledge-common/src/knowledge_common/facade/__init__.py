"""
跨服务接口：统一放在 knowledge_common.facade.api。

- VO：提供者定义，消费者直接引用，禁止在子项目重复定义
- Feign Client：写在消费方 infra/rpc/<项目>/client（如 admin EmbeddingClient），用 FeignClient 声明服务名
- 调用实现：knowledge_common.common.feign（Feign）
"""
