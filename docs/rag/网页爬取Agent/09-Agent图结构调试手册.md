# 网页爬取 Agent — 图结构调试手册（As-Built）

> **源码入口**
> - 根图：`agents/crawler_agent/graph.py` → `get_root_graph`
> - Supervisor：`agents/crawler_agent/workers/supervisor/deep_agent.py`
> - Planning：`agents/crawler_agent/workers/planning/graph.py`
> - 面客 SSE：`agents/service/crawler_agent_service.py`
> - 工具清单：`agents/tools/__init__.py`
> - Prompt：`configs/prompts.yaml`（`crawler.supervisor` / `crawler.planning`）

---

## 一、图拓扑（现状）

```
get_root_graph()
  └── get_deep_supervisor_graph()   # create_deep_agent
        ├── model + crawler_model_middleware
        ├── crawler_state_sync_middleware
        ├── tools: CRAWL_AGENT_DEEP_SUPERVISOR_TOOLS
        ├── interrupt_on: 7 个写工具
        ├── checkpointer
        └── subagents:
              └── planning_agent (CompiledSubAgent)
                    └── create_agent + PLANNING_TOOLS
                          + planning_system_prompt
                          + ModelCallLimitMiddleware
```

**没有** analysis / interaction / generation 三子图父包装；早期 `nodes/crawler_nodes` 为空壳，勿再按旧手册排查。

---

## 二、本地调试检查清单

1. **确认根图**  
   `get_root_graph` 是否就是 Supervisor 单例；改 HITL/工具后是否需重启进程清单例。

2. **模型**  
   管理端适配点 `web_crawler_agent` 是否启用；`GET /crawler/chat/models` 是否非空。

3. **Prompt**  
   修改 `prompts.yaml` 后确认 `prompt_config` 热更新/重启策略。

4. **Checkpointer**  
   Redis 可达；同一 `session_id`/thread_id 才能 resume HITL。

5. **试爬门禁**  
   正式 `crawl_execute` 前是否已有 Redis 指纹；失败时看工具返回文案而非只看前端。

6. **SSE 溯源**  
   事件 `source=subagent` 属于 Planning；Supervisor 工具在 `supervisor`。

---

## 三、典型执行路径

### 路径 A：新爬成功

```
message → Supervisor
  → task(planning_agent)
       → fetch_* / probe / anti / proxy → trial_crawl
       → 终稿含 crawl_config → state sync
  → AI 汇报策略 → END
用户：「爬取」
  → crawl_execute → interrupt (user_choice)
resume approve
  → 建任务 + MQ → END
```

### 路径 B：HITL 拒绝

```
crawl_execute interrupt → resume reject → 工具不执行 → Supervisor 继续对话
```

### 路径 C：Planning 触顶

```
ModelCallLimitMiddleware run_limit 到达 → Planning 强制结束
→ Supervisor 收到子 Agent 结果（可能不完整）→ 应提示用户缩小范围或补充信息
```

### 路径 D：失败修复

```
query_crawl_task → state.failed_*
→ task(planning) 针对失败 URL
→ crawl_retry + HITL → PENDING
```

### 路径 E：改范围

```
pause → planning → preview_scope_removal → apply_scope_change + HITL
```

---

## 四、状态字段速查

| 字段 | 写入方 | 用途 |
|------|--------|------|
| `target_url` | query / execute 入参 | 当前种子 |
| `task_id` | query / execute | 关联任务 |
| `crawl_config` | query / Planning 终稿 | 策略 |
| `failed_urls` / `failed_reason` | query | 修复上下文 |
| `messages` | Supervisor only | 对话 |

---

## 五、常见问题

| 现象 | 排查 |
|------|------|
| 前端点确认无反应 | 是否误调 `/confirm`；应 `resume` + approve |
| 一直无法正式爬 | trial 指纹、include_patterns 与 seed、会话是否一致 |
| Planning 工具在 Supervisor 侧出现 | Prompt/工具集配错；Supervisor 不应挂探站工具 |
| resume 报找不到 checkpoint | thread_id/session 不一致或 Redis 丢数据 |
| 任务 FAILED 用户焦虑 | 说明规则重试中；仅 USER_DECISION 需人工 |
| deepagents state 丢字段 | 确认 `state_schema` 映射补丁仍在（见 deep_agent.py） |

---

## 六、测试入口

- 单测/回归：`knowledge-content/tests/test_crawler_agent_*.py`
- 脚本：`scripts/run_crawler_agent_tests.sh`、`scripts/run_crawler_agent_integration_tests.sh`

调试时优先看日志前缀 `[CrawlerAgent]` 与工具返回 JSON，再对前端 SSE 事件。
