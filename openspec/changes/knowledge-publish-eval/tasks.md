## 1. Content: remove auto-promote + facades

- [x] 1.1 Delete `auto_promote_completed_canary` call path, scheduler hook, and `embedding_auto_publish_job` registration/SQL
- [x] 1.2 Expose internal/facade `promote(embedding_task_id)` (reuse `EmbeddingPublishService.promote_task`); no content-side operator publish UI
- [x] 1.3 Expose embedding-task query facade for COMPLETED canary binding (list/detail)
- [x] 1.4 Implement segment list/get/search by `doc_id` + optional `release_tag`/`task_id` (shared by MCP and facade); enforce get batch limit K

## 2. Document segment MCP

- [x] 2.1 Add MCP server/adapter in content (or thin adapter) exposing `list_document_segments`, `get_document_segments`, `search_document_segments`
- [x] 2.2 Wire MCP tools to the shared segment query implementation from 1.4

## 3. Retrieval: canary-aware Agent + eval exit

- [x] 3.1 Pass `releaseTag` (default prod) and optional `taskId` from chat/eval entry through Agent state into hybrid retrieve middleware
- [x] 3.2 Add non-streaming eval facade/API returning `{answer, contexts}` for admin batch scoring
- [x] 3.3 Verify online SSE chat without overrides still retrieves prod only

## 4. Admin: eval schema + dataset generation

- [x] 4.1 Add SQL + DO/DAO for `knowledge_eval_dataset` and `knowledge_eval_dataset_item` (shared DB)
- [x] 4.2 Implement dataset create flow: select one doc + name → start generation Agent (no blank dataset / no manual item create)
- [x] 4.3 Implement generation Agent in admin: MCP list→get/search, hard-coded quota 20–40 at 1:2:1, keypoints→items with excerpts/`used_chunk_ids`, budgets + degrade sampling
- [x] 4.4 Implement item edit APIs (question/ground_truth/excerpts/`enabled` only); reject manual add and incremental top-up generation

## 5. Admin: eval task, Ragas runs, publish

- [x] 5.1 Add SQL + DO/DAO for `knowledge_eval_task`, `knowledge_eval_run`, `knowledge_eval_run_item`
- [x] 5.2 Implement eval task create (dataset + embedding_task_id same doc), dataset swap while OPEN, list/detail
- [x] 5.3 Implement async run: snapshot enabled items → RPC retrieval eval (canary+taskId) → Ragas metrics → persist run/run_item; FAILED keeps task OPEN
- [x] 5.4 Implement report read APIs (summary + per-item); runs append-only
- [x] 5.5 Implement publish: require historical ≥1 SUCCESS run → RPC content.promote → on success ARCHIVED; reject publish/swap/rerun when ARCHIVED
- [x] 5.6 POC Ragas on target Python version; pin judge model configuration

## 6. Integration + ops

- [ ] 6.1 End-to-end: generate → human edit → canary run SUCCESS → publish → archive; confirm auto-promote gone
- [x] 6.2 Add admin permissions/menus for dataset, eval task, report, publish as needed
- [x] 6.3 Update operator notes: no content manual promote; canary stays until eval publish
