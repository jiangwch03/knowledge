# 爬虫 Agent 改造实施计划

> 状态：**代码与单测已收口**；仅剩真机 E2E 需 LLM+Redis 环境人工验收。

---

## 目标架构（改造后）

```text
START → url_preprocess → ingest_user → supervisor(deepagents) → state_sync
      → interrupt_gate → (supervisor | END)

planning_subgraph: NEED_USER_INPUT → end → 用户 chat 补充 → 再委派
```

---

## Phase 1～5 状态

| Phase | 状态 |
|-------|------|
| 1 准备 deepagents | ✅ |
| 2 Planning | ✅ |
| 3 Supervisor + 父图 | ✅ |
| 4 SSE / interrupt / 单测 | ✅（真机 E2E 见联调清单） |
| 5 rescope | ✅ |

---

## 验收 & 测试

```bash
chmod +x scripts/run_crawler_agent_tests.sh
./scripts/run_crawler_agent_tests.sh          # 单元 + 流式 smoke（默认跳过 integration）
./scripts/run_crawler_agent_integration_tests.sh  # 可选：真实 HTTP 探站用例
```

| 脚本 | 覆盖 |
|------|------|
| `run_crawler_agent_tests.sh` | architecture / interrupt / rescope / graph_smoke / sensitive_mask / streaming |
| `run_crawler_agent_integration_tests.sh` | milvus.io 真实 HTTP（需外网） |

真机 E2E（需 LLM + Redis）：`docs/rag/爬虫Agent_E2E联调清单.md`

---

## 已交付的非代码项

- dev 代理池示例：`sql/seed_crawl_proxy_pool_dev.sql`
- 敏感信息落库脱敏：`agents/utils/sensitive_mask_util.py`（HumanMessage 入库前）
- Supervisor / Planning 完整 prompt：`prompts.yaml`

---

## Legacy

已删除旧 analysis / execute 子图、url_router、手写 Supervisor 子图与 `task_planning` 工具；仅保留 deepagents 路径。
