# 爬虫 Agent E2E 联调清单

> deepagents 默认路径：`url_preprocess → ingest → supervisor → state_sync → interrupt_gate`

## 前置

- [ ] Redis + DB 可用，Checkpointer 正常
- [ ] `knowledge-content` 服务启动，模型适配器已配置
- [ ] （可选）执行 `sql/seed_crawl_proxy_pool_dev.sql` 配置 dev 代理

## 场景 1：新站 init 爬取

1. 发送：`帮我爬 https://milvus.io/docs/zh`
2. 期望：Planning 探站 → 产出 `strategy_summary` → **策略确认 interrupt（yes/no）**
3. 点确认 → **crawl_execute HITL** → 确认 → 返回 `task_id`
4. `query_crawl_task` 可查进度

## 场景 2：二类参数补充（登录/范围）

1. 目标站需登录时，Planning 输出 `NEED_USER_INPUT`
2. 期望：**不弹 yes/no**；Agent 转述问题后 **本轮结束**
3. 用户在输入框发送：`Cookie: ...` 或 `只爬 /docs/zh`
4. 再次委派 Planning → 产出策略 → 走场景 1 确认流

## 场景 3：rescope

1. 任务 RUNNING → `pause_crawl_task`
2. 发送：`不要爬博客了，只要 API 文档`
3. `task(planning_agent, mode=rescope)` → **删页确认 interrupt** → `apply_scope_change` HITL
4. 任务恢复 RUNNING，越界 URL 已软删

## 场景 4：fix 失败

1. 失败任务 → `task(mode=fix)` → 新策略 → `crawl_retry`

## 场景 5：SSE

- [ ] Planning 子图 token 打字机可见
- [ ] tool_call 卡片正常
- [ ] `user_choice`：choice 模式按钮 / text 模式文本框

## 自动化单测

```bash
./scripts/run_crawler_agent_tests.sh                 # 默认全绿（无 LLM/Redis/外网）
./scripts/run_crawler_agent_integration_tests.sh     # 可选：真实 HTTP 探站
```

真机 E2E 仍需本清单场景 1～5 人工跑一遍并勾选上方前置项。
