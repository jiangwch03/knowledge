from pathlib import Path

import yaml
from knowledge_common.utils.log_util import logger


class PromptConfig:
    """
    提示词配置管理器

    从 YAML 文件加载提示词配置，按功能点 key 提供访问。
    单例模式，由子项目启动时调用 load() 加载配置文件。

    使用方式：
        # 在子项目 server.py 启动时加载
        from knowledge_common.config.prompt_config import prompt_config
        prompt_config.load('src/configs/prompts.yaml')

        # 在业务代码中使用
        from knowledge_common.config.prompt_config import prompt_config
        system_prompt = prompt_config.get_system_prompt('txt_to_markdown')
    """

    _instance: 'PromptConfig | None' = None
    _prompts: dict[str, dict[str, str]] = {}
    _loaded: bool = False

    def __new__(cls) -> 'PromptConfig':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, file_path: str) -> None:
        """
        加载指定路径的提示词配置文件

        :param file_path: YAML 配置文件路径，支持相对路径（相对于 cwd）和绝对路径
        """
        prompts_file = Path(file_path)
        if not prompts_file.is_absolute():
            prompts_file = Path.cwd() / prompts_file

        if not prompts_file.exists():
            logger.warning(f'未找到提示词配置文件: {prompts_file}')
            return

        try:
            with open(prompts_file, encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                self._prompts = data
                self._loaded = True
                logger.info(f'提示词配置加载成功: {prompts_file}')
            else:
                logger.warning(f'提示词配置文件格式异常，期望 dict 实际 {type(data).__name__}')
        except Exception as e:
            logger.error(f'加载提示词配置失败: {e}')

    @property
    def is_loaded(self) -> bool:
        """配置是否已加载"""
        return self._loaded

    def get(self, key: str, field: str = 'system') -> str | None:
        """
        获取指定功能点的提示词

        :param key: 功能点 key，如 'txt_to_markdown'
        :param field: 提示词字段，默认 'system'
        :return: 提示词内容，未找到返回 None
        """
        config = self._prompts.get(key)
        if not config:
            return None
        return config.get(field)

    def get_system_prompt(self, key: str) -> str | None:
        """
        获取指定功能点的 system 提示词（快捷方法）

        :param key: 功能点 key
        :return: system 提示词内容
        """
        return self.get(key, field='system')


# 模块级单例，供业务层直接导入使用
prompt_config = PromptConfig()
