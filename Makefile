# =============================================================================
# Knowledge 项目根 Makefile
# 统一"消息流服务"等公共能力的开发入口
# 用法:make <target>,或 make help 查看全部目标
# =============================================================================

# 强制使用 bash(避免 zsh 在某些边界行为差异)
SHELL := /bin/bash

# Python 解释器(uv workspace 已绑定 .venv)
PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest

# 项目根路径
ROOT := $(shell pwd)

# 测试路径
TEST_MSG_STREAM := knowledge-common/tests/test_message_stream.py
TEST_COMMON_DIR := knowledge-common/tests
TEST_ALL_DIRS := knowledge-common/tests knowledge-admin/tests knowledge-rag/tests

# 默认目标:显示帮助
.DEFAULT_GOAL := help

# 假目标(不生成同名文件)
.PHONY: help \
        test-msg-stream test-msg-stream-quiet test-msg-stream-mock \
        test-msg-stream-e2e test-msg-stream-collect test-msg-stream-skip-redis \
        msg-stream-verify msg-stream-audit \
        test-common test-all \
        clean-pyc

# -----------------------------------------------------------------------------
# 帮助
# -----------------------------------------------------------------------------
help: ## 显示全部可用目标(执行 make help)
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║  Knowledge 项目 - 开发入口                                  ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "📦 消息流服务(MessageStreamService)"
	@echo "  make test-msg-stream         跑全部 47 项测试(verbose)"
	@echo "  make test-msg-stream-quiet   跑全部 47 项测试(仅结果)"
	@echo "  make test-msg-stream-mock    只跑 46 项 Mock/静态层(不需 Redis)"
	@echo "  make test-msg-stream-e2e     只跑 1 项真 Redis 端到端"
	@echo "  make test-msg-stream-skip-redis  跑除真 Redis 端到端外的全部 46 项"
	@echo "  make test-msg-stream-collect pytest --collect-only(看 47 个用例都被发现)"
	@echo "  make msg-stream-verify       离线 import 自检(不需 pytest/Redis,5s)"
	@echo "  make msg-stream-audit        跑前诚实审计(git diff 改了什么)"
	@echo ""
	@echo "🧪 全量测试"
	@echo "  make test-common             跑 knowledge-common 全部测试"
	@echo "  make test-all                跑全部子项目测试"
	@echo ""
	@echo "🧹 工具"
	@echo "  make clean-pyc               清理 __pycache__ / .pytest_cache"
	@echo ""

# -----------------------------------------------------------------------------
# 消息流服务测试 - 全量 / 安静 / 分层
# -----------------------------------------------------------------------------
test-msg-stream: ## 跑消息流服务全部 47 项测试(verbose)
	@echo "▶ 跑 $(TEST_MSG_STREAM) (verbose)"
	$(PYTEST) $(TEST_MSG_STREAM) -v

test-msg-stream-quiet: ## 跑消息流服务全部 47 项测试(仅结果)
	@echo "▶ 跑 $(TEST_MSG_STREAM) (quiet)"
	$(PYTEST) $(TEST_MSG_STREAM)

test-msg-stream-mock: ## 只跑 Mock/静态层(46 项,不需 Redis)
	@echo "▶ 跑 Mock/静态层(-k 'not EndToEnd')"
	$(PYTEST) $(TEST_MSG_STREAM) -v -k "not EndToEnd"

test-msg-stream-e2e: ## 只跑真 Redis 端到端(1 项)
	@echo "▶ 跑真 Redis 端到端"
	$(PYTEST) $(TEST_MSG_STREAM)::Test77EndToEndRealRedis -v -s

test-msg-stream-skip-redis: ## 跑除真 Redis 端到端外的全部 46 项
	@echo "▶ 跑除真 Redis 端到端外的全部 46 项"
	$(PYTEST) $(TEST_MSG_STREAM) -v -k "not EndToEnd" --tb=short

test-msg-stream-collect: ## pytest --collect-only,确认 47 个用例都被发现
	@echo "▶ 收集测试用例(--collect-only)"
	$(PYTEST) $(TEST_MSG_STREAM) --collect-only -q

# -----------------------------------------------------------------------------
# 消息流服务 - 离线自检 / 审计
# -----------------------------------------------------------------------------
msg-stream-verify: ## 离线 import 自检(不需 pytest/Redis,5s 完成)
	@echo "▶ 离线 import 自检"
	@$(PYTHON) -c "from knowledge_common.message_stream import (MessageStreamService, consumer, Message, MessageStreamError, ConsumerInfo); from knowledge_common.message_stream.backends.redis_stream import RedisStreamBackend; from knowledge_common.message_stream.backends.base import StreamBackend; print('✅ 全部核心类 / 装饰器 / 后端 可 import')"
	@echo ""
	@echo "▶ 编译检查"
	@$(PYTHON) -m py_compile $(TEST_MSG_STREAM) && echo "✅ $(TEST_MSG_STREAM) 语法 OK"
	@echo ""
	@echo "▶ 用例收集"
	@$(PYTEST) $(TEST_MSG_STREAM) --collect-only -q 2>&1 | tail -3

msg-stream-audit: ## 跑前诚实审计:看本次会话到底改了什么
	@echo "▶ 本次会话 git status"
	@git status --short
	@echo ""
	@echo "▶ 各区域 diff 行数(应只动 tests / docs / openspec,不动 message_stream 源码)"
	@git diff --stat 2>/dev/null || echo "(当前无未提交修改)"
	@echo ""
	@echo "▶ 框架源码 message_stream/ 是否被改(预期: 0 改动)"
	@git diff --stat knowledge-common/src/knowledge_common/message_stream/ 2>/dev/null | tail -1 || echo "✅ 未改动"
	@echo ""
	@echo "▶ admin lifespan 接入是否被改(预期: 0 改动)"
	@git diff --stat knowledge-admin/src/knowledge_admin/server/server.py 2>/dev/null | tail -1 || echo "✅ 未改动"

# -----------------------------------------------------------------------------
# 全量测试
# -----------------------------------------------------------------------------
test-common: ## 跑 knowledge-common 全部测试
	@echo "▶ 跑 knowledge-common 全部测试"
	$(PYTEST) $(TEST_COMMON_DIR) -v

test-all: ## 跑全部子项目测试
	@echo "▶ 跑全部子项目测试"
	$(PYTEST) $(TEST_ALL_DIRS) -v 2>&1 | tail -50

# -----------------------------------------------------------------------------
# 工具
# -----------------------------------------------------------------------------
clean-pyc: ## 清理 __pycache__ / .pytest_cache / .mypy_cache
	@echo "▶ 清理缓存"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ 缓存已清理"
