## 1. Schema and foundation

- [x] 1.0 Run standalone SQL `sql/upgrade_document_embedding_adapter.sql` (adapter.dimensions + text-embedding-v4 + document_embedding@1024); adapter admin UI validates dimensions
- [x] 1.1 Add SQL for embedding_task, segment (release_tag on segment only, aligned with Milvus), menu seeds — no release_tag on doc/task tables
- [x] 1.2 Add DO/DAO/Enum/VO; release_tag for segment/Milvus
- [x] 1.3 Add `pymilvus[model]>=2.6.9,<3.0.0` and `langchain-text-splitters>=1.1.1,<2.0.0`; scalar index on Milvus release_tag

## 2. Splitters

- [x] 2.1 DocumentSplitParam, SplitType, Factory
- [x] 2.2 TITLE/SMART parent-child splitter
- [x] 2.3 LENGTH / SEPARATOR / REGEX with oversize fallback
- [x] 2.4 Unit tests

## 3. Preview and catalog APIs

- [x] 3.1 GET strategies + model-info
- [x] 3.2 POST preview
- [x] 3.3 Permissions

## 4. Task pipeline

- [x] 4.1 Create task + in-progress guard + enqueue
- [x] 4.2 Split service: replace old canary only; never touch prod
- [x] 4.3 Consumer state machine
- [x] 4.4 Vector store: write with release_tag=canary
- [x] 4.5 Task list/detail/segments + FAILED retry
- [x] 4.6 Scheduler兜底

## 5. Frontend

- [x] 5.1 Config page + API
- [x] 5.2 List Embedding buttons
- [x] 5.3 Task page: release_tag aggregated from segments by task_id + polling
- [x] 5.4 Menu seeds

## 6. Verification

- [x] 6.1 Preview no persist; submit → VECTOR_STORED + canary
- [x] 6.2 New canary does not delete prod; old canary replaced
- [x] 6.3 Manual acceptance checklist
