"""
models.dev 本地 Profile 缓存

- 定时任务每日拉取 https://models.dev/api.json
- 按 model_code 建本地索引（不依赖厂商 SDK / init_chat_model provider）
- 同名模型优先取官方源，聚合网关（302ai 等）靠后
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from knowledge_common.config.env import UploadConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.url_util import UrlUtil
from knowledge_common.vo.model_profile_vo import ModelProfileVo

MODELS_DEV_API_URL = 'https://models.dev/api.json'

# 官方/一等源优先（分值越小越优先）；未列出的聚合商默认 1000
_PROVIDER_RANK: dict[str, int] = {
    'openai': 10,
    'anthropic': 10,
    'deepseek': 10,
    'alibaba-cn': 10,
    'alibaba': 20,
    'google': 10,
    'google-vertex': 20,
    'azure': 30,
    'azure-cognitive-services': 40,
    'xai': 10,
    'mistral': 10,
    'groq': 30,
    'cohere': 20,
    'together': 40,
    'fireworks-ai': 40,
    'openrouter': 50,
}

# 管理端字典 provider → models.dev provider id（用于同分时偏好）
_APP_PROVIDER_ALIAS: dict[str, str] = {
    'openai': 'openai',
    'DashScope': 'alibaba-cn',
    'dashscope': 'alibaba-cn',
}


class ModelsDevProfileService:
    """models.dev Profile 同步与查询"""

    _lock = threading.RLock()
    _index: dict[str, dict[str, Any]] | None = None
    _loaded_mtime: float | None = None

    @classmethod
    def _cache_dir(cls) -> Path:
        path = Path(UploadConfig.UPLOAD_PATH) / 'models_dev'
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def _index_path(cls) -> Path:
        return cls._cache_dir() / 'profile_index.json'

    @classmethod
    def _meta_path(cls) -> Path:
        return cls._cache_dir() / 'meta.json'

    @classmethod
    def _provider_rank(cls, provider_id: str) -> int:
        return _PROVIDER_RANK.get(provider_id, 1000)

    @classmethod
    def _bool_to_yn(cls, val: Any) -> str:
        """将 bool/None 转为 Y/N。None（未知）按不支持落成 N，保证前端可完整回填落库。"""
        return 'Y' if val is True else 'N'

    @classmethod
    def _map_model_raw(cls, provider_id: str, model: dict[str, Any]) -> dict[str, Any]:
        """将 models.dev 单模型原始数据映射为统一 Profile 字段。"""
        modalities = model.get('modalities') or {}
        inputs = {str(x).lower() for x in (modalities.get('input') or [])}
        outputs = {str(x).lower() for x in (modalities.get('output') or [])}
        limits = model.get('limit') or {}

        text_inputs = 'text' in inputs
        image_inputs = 'image' in inputs
        audio_inputs = 'audio' in inputs
        video_inputs = 'video' in inputs
        pdf_inputs = 'pdf' in inputs
        text_outputs = 'text' in outputs
        image_outputs = 'image' in outputs
        audio_outputs = 'audio' in outputs
        video_outputs = 'video' in outputs

        tool_calling = model.get('tool_call')
        reasoning = model.get('reasoning')
        structured = model.get('structured_output')
        attachment = bool(model.get('attachment'))

        return {
            'provider': provider_id,
            'model_id': model.get('id'),
            'max_input_tokens': limits.get('context'),
            'max_output_tokens': limits.get('output'),
            'text_inputs': text_inputs,
            'image_inputs': image_inputs,
            'audio_inputs': audio_inputs,
            'video_inputs': video_inputs,
            'text_outputs': text_outputs,
            'image_outputs': image_outputs,
            'audio_outputs': audio_outputs,
            'video_outputs': video_outputs,
            'reasoning_output': reasoning,
            'tool_calling': tool_calling,
            # models.dev 无独立 tool_choice 字段，工具调用能力存在时视为支持
            'tool_choice': tool_calling,
            'structured_output': structured,
            'image_url_inputs': image_inputs,
            'pdf_inputs': pdf_inputs,
            'pdf_tool_message': pdf_inputs and attachment,
            'image_tool_message': image_inputs and attachment,
        }

    @classmethod
    def build_index(cls, api_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """从 models.dev api.json 构建 model_id → profile 索引。"""
        index: dict[str, dict[str, Any]] = {}
        for provider_id, provider in api_data.items():
            if not isinstance(provider, dict):
                continue
            models = provider.get('models')
            if not isinstance(models, dict):
                continue
            for model_id, model in models.items():
                if not isinstance(model, dict):
                    continue
                mapped = cls._map_model_raw(str(provider_id), model)
                mapped['model_id'] = model_id
                existing = index.get(model_id)
                if existing is None:
                    index[model_id] = mapped
                    continue
                if cls._provider_rank(str(provider_id)) < cls._provider_rank(str(existing.get('provider') or '')):
                    index[model_id] = mapped
        return index

    @classmethod
    def _write_index(cls, index: dict[str, dict[str, Any]]) -> None:
        index_path = cls._index_path()
        meta_path = cls._meta_path()
        tmp_index = index_path.with_suffix('.json.tmp')
        tmp_meta = meta_path.with_suffix('.json.tmp')
        tmp_index.write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
        tmp_index.replace(index_path)
        meta = {
            'synced_at': datetime.now().isoformat(timespec='seconds'),
            'source': MODELS_DEV_API_URL,
            'model_count': len(index),
        }
        tmp_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp_meta.replace(meta_path)
        with cls._lock:
            cls._index = index
            cls._loaded_mtime = index_path.stat().st_mtime

    @classmethod
    def _load_index_from_disk(cls) -> dict[str, dict[str, Any]]:
        index_path = cls._index_path()
        if not index_path.exists():
            return {}
        try:
            data = json.loads(index_path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return {}
            return data
        except Exception as e:
            logger.warning(f'读取 models.dev 本地索引失败: {e}')
            return {}

    @classmethod
    def get_index(cls) -> dict[str, dict[str, Any]]:
        """获取内存索引；文件更新后自动热加载。"""
        index_path = cls._index_path()
        mtime = index_path.stat().st_mtime if index_path.exists() else None
        with cls._lock:
            if cls._index is not None and cls._loaded_mtime == mtime:
                return cls._index
            loaded = cls._load_index_from_disk()
            cls._index = loaded
            cls._loaded_mtime = mtime
            return loaded

    @classmethod
    async def sync_from_remote(cls) -> dict[str, Any]:
        """拉取 models.dev 并刷新本地索引。"""
        logger.info(f'开始同步 models.dev: {MODELS_DEV_API_URL}')
        api_data = await UrlUtil.async_http_get(MODELS_DEV_API_URL, dict, timeout=120)
        if not isinstance(api_data, dict) or not api_data:
            raise ServiceException(message='models.dev 返回数据为空')

        index = await asyncio.to_thread(cls.build_index, api_data)
        await asyncio.to_thread(cls._write_index, index)
        meta = {
            'synced_at': datetime.now().isoformat(timespec='seconds'),
            'model_count': len(index),
        }
        logger.info(f'models.dev 同步完成: model_count={len(index)}')
        return meta

    @classmethod
    async def ensure_index(cls) -> dict[str, dict[str, Any]]:
        """若本地无索引则尝试同步一次。"""
        index = cls.get_index()
        if index:
            return index
        try:
            await cls.sync_from_remote()
        except Exception as e:
            logger.warning(f'models.dev 首次同步失败，将返回空 Profile: {e}')
            return {}
        return cls.get_index()

    @classmethod
    def _pick_entry(
        cls,
        index: dict[str, dict[str, Any]],
        model_code: str,
        provider: str | None,
    ) -> dict[str, Any] | None:
        entry = index.get(model_code)
        if entry:
            return entry
        # 大小写不敏感兜底
        lower = model_code.lower()
        for key, value in index.items():
            if key.lower() == lower:
                return value
        # 若调用方 provider 能映射到 models.dev，尝试「provider/model」风格 id（少见）
        alias = _APP_PROVIDER_ALIAS.get(provider or '')
        if alias:
            composite = f'{alias}/{model_code}'
            if composite in index:
                return index[composite]
        return None

    @classmethod
    def to_profile_vo(cls, entry: dict[str, Any]) -> ModelProfileVo:
        def _get(key: str) -> Any:
            return entry.get(key)

        return ModelProfileVo(
            max_output_tokens=_get('max_output_tokens'),
            max_tokens=_get('max_output_tokens'),
            max_input_tokens=_get('max_input_tokens'),
            support_reasoning=cls._bool_to_yn(_get('reasoning_output')),
            support_images=cls._bool_to_yn(_get('image_inputs')),
            support_text_inputs=cls._bool_to_yn(_get('text_inputs')),
            support_audio_inputs=cls._bool_to_yn(_get('audio_inputs')),
            support_video_inputs=cls._bool_to_yn(_get('video_inputs')),
            support_text_outputs=cls._bool_to_yn(_get('text_outputs')),
            support_image_outputs=cls._bool_to_yn(_get('image_outputs')),
            support_audio_outputs=cls._bool_to_yn(_get('audio_outputs')),
            support_video_outputs=cls._bool_to_yn(_get('video_outputs')),
            support_tool_call=cls._bool_to_yn(_get('tool_calling')),
            support_tool_choice=cls._bool_to_yn(_get('tool_choice')),
            support_structured_output=cls._bool_to_yn(_get('structured_output')),
            support_image_url_inputs=cls._bool_to_yn(_get('image_url_inputs')),
            support_pdf_inputs=cls._bool_to_yn(_get('pdf_inputs')),
            support_pdf_tool_message=cls._bool_to_yn(_get('pdf_tool_message')),
            support_image_tool_message=cls._bool_to_yn(_get('image_tool_message')),
            text_inputs=_get('text_inputs'),
            image_inputs=_get('image_inputs'),
            audio_inputs=_get('audio_inputs'),
            video_inputs=_get('video_inputs'),
            text_outputs=_get('text_outputs'),
            image_outputs=_get('image_outputs'),
            audio_outputs=_get('audio_outputs'),
            video_outputs=_get('video_outputs'),
            reasoning_output=_get('reasoning_output'),
            tool_calling=_get('tool_calling'),
            tool_choice=_get('tool_choice'),
            structured_output=_get('structured_output'),
            image_url_inputs=_get('image_url_inputs'),
            pdf_inputs=_get('pdf_inputs'),
            pdf_tool_message=_get('pdf_tool_message'),
            image_tool_message=_get('image_tool_message'),
        )

    @classmethod
    async def get_model_profile(
        cls,
        model_code: str,
        provider: str | None = None,
    ) -> ModelProfileVo:
        index = await cls.ensure_index()
        entry = cls._pick_entry(index, model_code, provider)
        if not entry:
            return ModelProfileVo()
        return cls.to_profile_vo(entry)
