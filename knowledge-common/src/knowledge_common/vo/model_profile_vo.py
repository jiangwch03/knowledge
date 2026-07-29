from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ModelProfileVo(BaseModel):
    """
    模型 Profile 返回结构，由 LangChain init_chat_model 的 .profile 映射而来
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    max_tokens: int | None = Field(default=None, description='最大输出token')
    # 兼容：LangChain profile 字段名 max_output_tokens
    max_output_tokens: int | None = Field(default=None, description='最大输出token')
    # LangChain 官方语义：max_input_tokens = Maximum context window
    max_input_tokens: int | None = Field(default=None, description='最大输入token数（上下文窗口）')

    # 直接透出 LangChain profile 的能力原始字段（用于排查“字段不全”）
    text_inputs: bool | None = Field(default=None, description='是否支持文本输入')
    image_inputs: bool | None = Field(default=None, description='是否支持图像输入')
    audio_inputs: bool | None = Field(default=None, description='是否支持音频输入')
    video_inputs: bool | None = Field(default=None, description='是否支持视频输入')
    text_outputs: bool | None = Field(default=None, description='是否支持文本输出')
    image_outputs: bool | None = Field(default=None, description='是否支持图像输出')
    audio_outputs: bool | None = Field(default=None, description='是否支持音频输出')
    video_outputs: bool | None = Field(default=None, description='是否支持视频输出')
    reasoning_output: bool | None = Field(default=None, description='是否支持推理输出')
    tool_calling: bool | None = Field(default=None, description='是否支持工具调用')
    tool_choice: bool | None = Field(default=None, description='是否支持工具选择')
    structured_output: bool | None = Field(default=None, description='是否支持结构化输出')
    image_url_inputs: bool | None = Field(default=None, description='是否支持图像URL输入')
    pdf_inputs: bool | None = Field(default=None, description='是否支持PDF输入')
    pdf_tool_message: bool | None = Field(default=None, description='是否支持PDF工具消息')
    image_tool_message: bool | None = Field(default=None, description='是否支持图像工具消息')

    # 项目使用的能力字段（Y/N，供前端配置落库）
    support_reasoning: str | None = Field(default=None, description='是否支持推理 Y/N')
    support_images: str | None = Field(default=None, description='是否支持图片/图像输入 Y/N')
    support_text_inputs: str | None = Field(default=None, description='是否支持文本输入 Y/N')
    support_audio_inputs: str | None = Field(default=None, description='是否支持音频输入 Y/N')
    support_video_inputs: str | None = Field(default=None, description='是否支持视频输入 Y/N')
    support_text_outputs: str | None = Field(default=None, description='是否支持文本输出 Y/N')
    support_image_outputs: str | None = Field(default=None, description='是否支持图像输出 Y/N')
    support_audio_outputs: str | None = Field(default=None, description='是否支持音频输出 Y/N')
    support_video_outputs: str | None = Field(default=None, description='是否支持视频输出 Y/N')
    support_image_url_inputs: str | None = Field(default=None, description='是否支持图像URL输入 Y/N')
    support_pdf_inputs: str | None = Field(default=None, description='是否支持PDF输入 Y/N')
    support_pdf_tool_message: str | None = Field(default=None, description='是否支持PDF工具消息 Y/N')
    support_image_tool_message: str | None = Field(default=None, description='是否支持图像工具消息 Y/N')
    support_tool_call: str | None = Field(default=None, description='是否支持工具调用 Y/N')
    support_tool_choice: str | None = Field(default=None, description='是否支持工具选择 Y/N')
    support_structured_output: str | None = Field(default=None, description='是否支持结构化输出 Y/N')
