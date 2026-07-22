from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ChatModelConfigModel(BaseModel):
    """
    ChatModel 工厂入参 VO

    与 LangChainModelFactory.create_chat_model 方法字段保持一致。
    仅包含工厂方法实际消费的核心模型参数，不含业务元数据。

    model_config 说明：
    - alias_generator=to_camel：序列化时自动将 snake_case 字段转为 camelCase（如 model_code → modelCode），
      用于兼容前端交互格式。
    - populate_by_name=True：反序列化时同时支持 alias（camelCase）和原始字段名（snake_case）传参。
      例如 ChatModelConfigModel(model_code="gpt-4") 和 ChatModelConfigModel(modelCode="gpt-4") 均可构造成功。
      开启此选项是为了让后端代码在构造 VO 时可以直接使用 snake_case 字段名，保持代码可读性。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    model_code: str = Field(description='模型编码')
    provider: str = Field(description='提供商')
    api_key: str = Field(description='API Key')
    base_url: str = Field(description='Base URL')
    temperature: float = Field(description='默认温度')
    max_tokens: int | None = Field(default=None, description='最大输出token')


class EmbeddingModelConfigModel(BaseModel):
    """
    Embedding 模型工厂入参 VO

    与 LangChainModelFactory.create_embedding_model 方法字段保持一致。
    仅包含工厂方法实际消费的核心模型参数，不含业务元数据。

    model_config 说明：
    - alias_generator=to_camel：序列化时自动将 snake_case 字段转为 camelCase。
    - populate_by_name=True：反序列化时同时支持 alias 和原始字段名传参，
      便于后端代码直接用 snake_case 字段构造对象。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    model_code: str = Field(description='模型编码')
    provider: str = Field(description='提供商')
    api_key: str = Field(description='API Key')
    base_url: str = Field(description='Base URL')
    dimensions: int = Field(description='向量维度')
    # 单次 Embedding API 请求条数；按模型上限配置（如通义 v4=10，OpenAI 可更大）
    chunk_size: int | None = Field(default=None, description='单次 API 请求文本条数')
    # OpenAI 兼容网关通常不接受 token id 数组，应关闭；官方 OpenAI 可开可关
    check_embedding_ctx_length: bool | None = Field(
        default=None,
        description='是否先做 ctx length token 预处理',
    )
