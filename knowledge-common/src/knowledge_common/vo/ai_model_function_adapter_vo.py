from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size

from knowledge_common.vo.base_page_query_vo import BasePageQueryModel


class AiModelFunctionAdapterModel(BaseModel):
    """
    模型功能适配表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    adapter_id: int | None = Field(default=None, description='适配ID')
    function_point: str | None = Field(default=None, description='业务功能点')
    param_id: str | None = Field(default=None, description='参数ID，唯一标识业务功能')
    model_id: str | None = Field(default=None, description='关联模型ID，多个用|分隔')
    dimensions: int | None = Field(default=None, description='向量维度（Embedding 业务适配必填）')
    model_code: str | None = Field(default=None, description='模型编码')
    model_name: str | None = Field(default=None, description='模型名称')
    model_type: str | None = Field(default=None, description='模型类型')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')
    del_flag: str | None = Field(default=None, description='删除标志')

    @NotBlank(field_name='function_point', message='业务功能点不能为空')
    @Size(field_name='function_point', min_length=0, max_length=100, message='业务功能点长度不能超过100个字符')
    def get_function_point(self) -> str | None:
        return self.function_point

    @NotBlank(field_name='param_id', message='参数ID不能为空')
    @Size(field_name='param_id', min_length=0, max_length=64, message='参数ID长度不能超过64个字符')
    def get_param_id(self) -> str | None:
        return self.param_id

    @NotBlank(field_name='model_id', message='模型ID不能为空')
    def get_model_id(self) -> str | None:
        return self.model_id


class AiModelFunctionAdapterPageQueryModel(BasePageQueryModel):
    """
    模型功能适配分页查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    function_point: str | None = Field(default=None, description='业务功能点')
    param_id: str | None = Field(default=None, description='参数ID')


class AiModelConfigModel(BaseModel):
    """
    按参数ID获取的模型配置模型

    包含业务元数据 + 模型技术参数，用于 DAO 层返回完整的适配配置信息。
    Service 层可从中提取技术参数构造 ChatModelConfigModel / EmbeddingModelConfigModel。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    adapter_id: int | None = Field(default=None, description='适配ID')
    function_point: str | None = Field(default=None, description='业务功能点')
    param_id: str | None = Field(default=None, description='参数ID')
    model_id: int | None = Field(default=None, description='模型ID')
    model_code: str | None = Field(default=None, description='模型编码')
    model_name: str | None = Field(default=None, description='模型名称')
    provider: str | None = Field(default=None, description='提供商')
    api_key: str | None = Field(default=None, description='API Key')
    base_url: str | None = Field(default=None, description='Base URL')
    model_type: str | None = Field(default=None, description='模型类型')
    max_tokens: int | None = Field(default=None, description='最大输出token')
    temperature: float | None = Field(default=0.7, description='默认温度')
    dimensions: int | None = Field(default=None, description='向量维度（来自业务适配）')
    support_reasoning: str | None = Field(default=None, description='是否支持推理')
    support_images: str | None = Field(default=None, description='是否支持图片/图像输入')
    support_text_inputs: str | None = Field(default=None, description='是否支持文本输入')
    support_audio_inputs: str | None = Field(default=None, description='是否支持音频输入')
    support_video_inputs: str | None = Field(default=None, description='是否支持视频输入')
    support_text_outputs: str | None = Field(default=None, description='是否支持文本输出')
    support_image_outputs: str | None = Field(default=None, description='是否支持图像输出')
    support_audio_outputs: str | None = Field(default=None, description='是否支持音频输出')
    support_video_outputs: str | None = Field(default=None, description='是否支持视频输出')
    support_tool_call: str | None = Field(default=None, description='是否支持工具调用')
    support_tool_choice: str | None = Field(default=None, description='是否支持工具选择')
    support_structured_output: str | None = Field(default=None, description='是否支持结构化输出')
    support_image_url_inputs: str | None = Field(default=None, description='是否支持图像URL输入')
    support_pdf_inputs: str | None = Field(default=None, description='是否支持PDF输入')
    support_pdf_tool_message: str | None = Field(default=None, description='是否支持PDF工具消息')
    support_image_tool_message: str | None = Field(default=None, description='是否支持图像工具消息')
    max_input_tokens: int | None = Field(default=None, description='最大输入token数（上下文窗口）')
