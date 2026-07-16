"""tests 目录 conftest

将 src 目录添加到 sys.path 最前面，确保真实的 knowledge_content 包优先于 tests/knowledge_content。
同时统一加载 .env 配置。
"""
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv


def pytest_configure(config):
    config.addinivalue_line('markers', 'integration: requires outbound network (milvus.io etc.)')

_PROJECT_ROOT = Path(__file__).resolve().parent  # knowledge-content/tests
_PROJECT_SRC = _PROJECT_ROOT.parent / 'src'       # knowledge-content/src
_PROJECT_DIR = _PROJECT_ROOT.parent                # knowledge-content

# 必须插入到最前面，否则 tests 目录下空的 knowledge_content 包会拦截导入
sys.path.insert(0, str(_PROJECT_SRC))
sys.path.insert(0, str(_PROJECT_DIR))

# 加载 .env 配置
_ENV_FILE = _PROJECT_SRC / 'configs' / '.env.dev'
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)
