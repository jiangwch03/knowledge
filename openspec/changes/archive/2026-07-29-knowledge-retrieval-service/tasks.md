## 1. Scaffold knowledge-retrieval

- [x] 1.1 Create `knowledge-retrieval/` package layout (mirror content: main/server/controller/service/vo/agents/…)
- [x] 1.2 Add `.env.dev` (`APP_NAME=knowledge-retrieval`, `APP_PORT=9101`)
- [x] 1.3 Register workspace member + `uv sync`
- [x] 1.4 Implement `create_app` lifespan (Redis/DB/dict/config/auth/Checkpointer as needed; **no** embedding consumers; **no** new QA consumers/schedulers)
- [x] 1.5 Add `scripts/start-retrieval.sh`

## 2. Milvus ACL + hybrid text index (content write path)

- [x] 2.1 Extend Milvus DDL: `dept_id`, `user_id` + scalar indexes; enable `text` full-text/BM25 (or equivalent)
- [x] 2.2 Update `DocumentVectorVo` / upsert path in `knowledge-content` to write ACL fields
- [x] 2.3 Document/implement stock vector backfill or rebuild procedure

## 3. Hybrid RetrieveService + search API

- [x] 3.1 Implement keyword extraction + vector ANN + text search + RRF fuse + threshold/top_k defaults (5 / 0.5)
- [x] 3.2 Filters: `releaseTag` (default prod), optional `taskId` (debug/RAGAS comments), data_scope via `dept_id`/`user_id`
- [x] 3.3 Parent expansion: parent text; `chunkId`/`hitChunkId`/`expandedFromChild`
- [x] 3.4 `POST /retrieval/search` + `rag:retrieve:query`; degrade to vector-only on keyword failure
- [x] 3.5 Unit/integration tests for filters, expansion, empty hits, degrade path

## 4. Topic dict + single QA Agent

- [x] 4.1 Seed dictionary topics: milvus / ai_production / langchain / langgraph
- [x] 4.2 Implement图内 `topic_gate` / `query_rewrite` middleware (`prompt_profile` + `need_retrieve` + `search_query`)
- [x] 4.3 Implement single Agent graph: rewrite → gate → conditional hybrid_retrieve + cs/knowledge prompt switch + `tavily_search` tool
- [x] 4.4 Seed `sys_config` `rag.tavily.api_key` as **empty/placeholder only** (no real key)
- [x] 4.5 Inherit `AgentChatService`; reuse `AgentSessionService`; thin session/chat controllers (crawler-shaped; skip resume unless needed)
- [x] 4.6 Permissions `rag:retrieve:chat` (+ session perms as needed); SSE citations vs web sources distinguished
- [x] 4.7 Tests: unrelated skips retrieve; related runs middleware; missing Tavily key degrades

## 5. Frontend knowledge QA

- [x] 5.1 Menu seed + vue page modeled on crawler session chat
- [x] 5.2 Wire session list/create/rename/close/delete, models, message SSE, message history to retrieval APIs

## 6. Docs and guardrails

- [x] 6.1 Keep `docs/rag/知识检索/01-需求设计.md` as source of truth; note OpenSpec aligned
- [x] 6.2 Confirm no retrieve orchestration inside admin AiChatService; no embedding consumers on retrieval
- [x] 6.3 Manual smoke: search + multi-turn QA + topic miss customer-service path
