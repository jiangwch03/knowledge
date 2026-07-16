import os
import re
from pathlib import Path
from typing import Any

import yaml
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.project_path_util import infer_current_project, resolve_workspace_root


_PROMTS_FILENAME = 'prompts.yaml'


def _find_prompts_file() -> str | None:
    """
    按优先级在多个候选路径中查找 prompts.yaml 文件

    优先级：
    1. cwd 向上回溯 src/configs/prompts.yaml
    2. workspace 下各 knowledge-* 子项目 src/configs/（当前项目优先）
    """
    candidates: list[str] = []

    # 1. 从 cwd 向上回溯，查找 src/configs/prompts.yaml
    current = os.getcwd()
    prev = None
    while current != prev:
        candidates.append(os.path.join(current, 'src', 'configs', _PROMTS_FILENAME))
        prev = current
        current = os.path.dirname(current)

    # 2. workspace 下各子项目的 src/configs/，优先检查推断出的当前项目
    workspace_root = resolve_workspace_root()
    current_project = infer_current_project()
    if workspace_root:
        try:
            entries = sorted(os.listdir(workspace_root))
            # 优先把推断出的当前项目放前面
            if current_project and current_project in entries:
                entries.remove(current_project)
                entries.insert(0, current_project)
            for entry in entries:
                project_path = os.path.join(workspace_root, entry)
                if os.path.isdir(project_path) and entry.startswith('knowledge-'):
                    candidates.append(
                        os.path.join(project_path, 'src', 'configs', _PROMTS_FILENAME)
                    )
        except Exception:
            pass

    seen: set[str] = set()
    for path in candidates:
        if path not in seen and os.path.isfile(path):
            return path
        seen.add(path)

    return None


class PromptConfig:
    """
    YAML 配置管理器

    从 YAML 文件加载配置，支持点号路径访问任意嵌套层级。
    最初用于提示词管理，目前已扩展为通用 YAML 配置读取器。
    单例模式，由子项目启动时调用 load() 加载配置文件。

    使用方式：
        # 在子项目 server.py 启动时加载
        from knowledge_common.config.prompt_config import prompt_config
        prompt_config.load()

        # 获取提示词（向后兼容）
        from knowledge_common.config.prompt_config import prompt_config
        system_prompt = prompt_config.get_system_prompt('txt_to_markdown')
        # 或使用点号路径：
        system_prompt = prompt_config.get('crawler.analysis')

        # 获取任意配置（通用方法）
        db_host = prompt_config.get_value('database.host')
    """

    _instance: 'PromptConfig | None' = None
    _prompts: dict[str, dict[str, str]] = {}
    _loaded: bool = False

    def __new__(cls) -> 'PromptConfig':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, file_path: str | None = None) -> None:
        """
        加载提示词配置文件

        支持两种模式：
        1. 传 file_path：使用指定路径（向后兼容）
        2. 不传或路径不存在：自动发现 src/configs/prompts.yaml

        :param file_path: 可选的 YAML 配置文件路径，不传则自动发现
        """
        prompts_file: Path | None = None

        if file_path:
            prompts_file = Path(file_path)
            if not prompts_file.is_absolute():
                prompts_file = Path.cwd() / prompts_file
            if not prompts_file.exists():
                logger.warning(f'指定的提示词配置文件不存在: {prompts_file}，尝试自动发现...')
                prompts_file = None

        if prompts_file is None:
            found = _find_prompts_file()
            if found:
                prompts_file = Path(found)
            else:
                logger.warning('未找到 prompts.yaml 配置文件，各提示词功能将返回默认值')
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
        获取指定配置的提示词或文本内容

        支持点号路径访问嵌套配置。

        处理逻辑：
        1. 通过点号路径定位到目标配置节点
        2. 若节点为 dict，提取 field 字段（默认 'system'）
        3. 若 field 值为 dict，视为 RICE 四段式并组合
        4. 否则直接返回字符串值

        :param key: 配置路径，支持点号嵌套，如 'crawler.analysis'
        :param field: 提取的字段名，默认 'system'
        :return: 提示词字符串，未找到返回 None
        """
        config = self._get_nested(self._prompts, key)
        if not config:
            return None

        value = config.get(field) if isinstance(config, dict) else config
        if isinstance(value, dict):
            # RICE 结构化提示词 → 组合
            return self._compose_rice(value)
        return value

    def get_value(self, key: str, default: Any = None) -> Any:
        """
        获取原始配置值（通用方法），不经过 RICE 组合

        适用于读取任意非提示词配置（数据库、Redis、日志等）。
        支持点号路径访问嵌套层级。

        :param key: 配置路径，支持点号嵌套
        :param default: 未找到时的默认值
        :return: 原始配置值
        """
        value = self._get_nested(self._prompts, key)
        return value if value is not None else default

    def _get_nested(self, data: dict, key: str) -> Any:
        """
        通过点号路径访问嵌套字典

        示例：
        - _get_nested(data, 'crawler.analysis.system')
          → data['crawler']['analysis']['system']
        - _get_nested(data, 'database.host')
          → data['database']['host']

        :param data: 嵌套字典
        :param key: 以点号分隔的路径
        :return: 对应值，路径不存在或中途遇到非 dict 时返回 None
        """
        if not key or not isinstance(key, str):
            return None
        parts = key.split('.')
        current: object = data
        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def get_system_prompt(self, key: str) -> str | None:
        """
        获取指定功能点的 system 提示词（快捷方法）

        :param key: 功能点 key
        :return: system 提示词内容
        """
        return self.get(key, field='system')

    # ──────────────────────────────────────────────
    # RICE 组合逻辑
    # ──────────────────────────────────────────────

    def _compose_rice(self, sections: dict) -> str:
        """
        将 RICE 分段 dict 通过 _common.rice_skeleton 组合为完整提示词

        :param sections: 包含 role / inputs / instruction / constraint / examples 的 dict
        :return: 组合后的提示词字符串
        """
        skeleton = self._prompts.get('_common', {}).get('rice_skeleton', '')
        if not skeleton:
            logger.error('[PromptConfig] RICE skeleton not found in _common.rice_skeleton')
            return ''

        text = skeleton

        # R – 角色定义
        text = text.replace('{role}', sections.get('role', '').strip())

        # I – 输入上下文（list → 逐行拼接）
        inputs = sections.get('inputs', [])
        if isinstance(inputs, list):
            inputs_text = '\n'.join(
                item.strip() if item.strip().startswith('-') else f'- {item.strip()}'
                for item in inputs
                if item.strip()
            )
        else:
            inputs_text = str(inputs).strip()
        text = text.replace('{inputs}', inputs_text)

        # I – 行为规范
        text = text.replace('{instruction}', sections.get('instruction', '').strip())

        # C – 边界要求（含 <<_common.xxx>> 占位符解析）
        constraint = sections.get('constraint', '').strip()
        constraint = self._resolve_placeholders(constraint)
        text = text.replace('{constraint}', constraint)

        # E – 案例说明
        text = text.replace('{examples}', sections.get('examples', '').strip())

        # 清理多余空行（段间保留一个空行）
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text

    def _resolve_placeholders(self, text: str) -> str:
        """
        解析文本中的 <<_common.xxx>> 占位符，替换为 _common 中对应内容

        支持多级路径：<<_common.json_constraints>>、<<_common.foo.bar>>
        """
        common = self._prompts.get('_common', {})

        def _replacer(m: re.Match) -> str:
            path = m.group(1)
            parts = path.split('.')
            val: object = common
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part, '')
                else:
                    return m.group(0)  # 无法解析，保持原样
            return str(val) if val else m.group(0)

        return re.sub(r'<<_common\.([^>]+)>>', _replacer, text)


# 模块级单例，供业务层直接导入使用
prompt_config = PromptConfig()
