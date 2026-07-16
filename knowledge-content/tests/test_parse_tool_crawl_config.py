"""工具入参 crawl_config：JSON 字符串解析与 dict 兼容"""

import json

import pytest

from knowledge_content.agents.utils.strategy_config_util import (
    _coerce_crawl_config_to_str,
    parse_tool_crawl_config,
)


def test_parse_json_string():
    assert parse_tool_crawl_config('{"a": 1, "b": {"c": true}}') == {
        'a': 1,
        'b': {'c': True},
    }


def test_parse_dict_passthrough():
    cfg = {'browser_config': {'headless': True}}
    assert parse_tool_crawl_config(cfg) is cfg


def test_parse_none_and_blank():
    assert parse_tool_crawl_config(None) is None
    assert parse_tool_crawl_config('  ') is None


def test_parse_invalid_raises():
    with pytest.raises(ValueError, match='JSON 对象'):
        parse_tool_crawl_config('[1,2]')
    with pytest.raises(ValueError, match='类型非法'):
        parse_tool_crawl_config(123)  # type: ignore[arg-type]


def test_coerce_dict_to_json_str():
    raw = {'needs_user_input': False}
    out = _coerce_crawl_config_to_str(raw)
    assert isinstance(out, str)
    assert json.loads(out) == raw


def test_coerce_str_passthrough():
    assert _coerce_crawl_config_to_str('{"a":1}') == '{"a":1}'
