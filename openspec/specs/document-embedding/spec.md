## Purpose

规范文档向量化（Embedding）任务提交、异步切分与向量写入、canary/prod 发布标签，以及任务列表与失败重试。

## Requirements

### Requirement: User can create embedding tasks from converted documents
The system SHALL allow authorized users to submit an embedding task for documents in CONVERTED, CHUNKED, or VECTOR_STORED status, rejecting concurrent in-progress tasks for the same doc_id.

#### Scenario: Submit creates PENDING task and enqueues work
- **WHEN** a user submits valid split parameters with no in-progress task
- **THEN** the system creates a PENDING knowledge_document_embedding_task and publishes embedding.pending

### Requirement: Embedding model dimensions come from business adapter
The system SHALL store and resolve embedding dimensions on the document_embedding function adapter (not on ai_models). Task/client APIs MUST NOT accept free-form dimensions.

#### Scenario: Adapter config carries dimensions
- **WHEN** a client requests embedding model info via document_embedding
- **THEN** the system returns model code and the adapter-configured dimensions

#### Scenario: document_embedding requires dimensions
- **WHEN** an admin saves document_embedding without a positive dimensions value
- **THEN** the system rejects the save

### Requirement: Async pipeline writes canary vectors without touching prod
The system SHALL asynchronously chunk then embed, write Milvus vectors with task_id and release_tag=canary, set document status VECTOR_STORED on success, and MUST NOT mutate or delete segments/vectors with release_tag=prod for the same doc_id. A new canary MAY replace a previous canary for that doc_id. Documents MUST NOT be deleted in this feature scope; only segments and vectors may be cleaned (old canary replacement, pending_delete async cleanup, failed-task residue).

#### Scenario: Parent segments are not written to Milvus
- **WHEN** the embedding phase runs
- **THEN** segments with skip_embedding=1 are not inserted into Milvus

#### Scenario: New canary leaves prod intact
- **WHEN** a document already has prod vectors and a new embedding task completes
- **THEN** prod vectors remain and the new batch is tagged canary

### Requirement: Schema uses release_tag for later gray publish
The system SHALL store release_tag on knowledge_document_segment and Milvus only (kept in sync), with values canary, prod, and pending_delete. The embedding task table and knowledge_document MUST NOT be the source of truth for release routing.

#### Scenario: Completed task data is canary
- **WHEN** an embedding task completes successfully
- **THEN** its segments and vectors use release_tag=canary

### Requirement: Embedding task list and segment review
The system SHALL provide APIs to list tasks, view detail, paginate segments, and retry FAILED tasks by creating a new task from original parameters.

#### Scenario: Retry failed task
- **WHEN** an authorized user retries a FAILED task
- **THEN** the system creates a new PENDING task and enqueues it

### Requirement: Milvus vectors carry dept_id and user_id
When embedding upsert writes `knowledge_document_vector` rows, the system SHALL persist `dept_id` and `user_id` aligned with the source document (upload user / document ownership fields as implemented), and SHALL maintain scalar indexes suitable for data_scope filters.

#### Scenario: New embedding task writes ACL fields
- **WHEN** a new embedding task flushes vectors to Milvus
- **THEN** each inserted/upserted row includes `dept_id` and `user_id`

### Requirement: Text field supports hybrid retrieval indexing
The Milvus collection schema/index setup SHALL enable full-text/BM25 (or equivalent sparse/text search) over the existing `text` field so hybrid retrieval can run a keyword channel in addition to dense ANN.

#### Scenario: Text channel usable after migration
- **WHEN** operators apply the updated Milvus DDL/migration
- **THEN** keyword/full-text search against `text` is available to the retrieval service

### Requirement: Existing vectors migration path
The system SHALL document or provide a migration path for existing vectors missing ACL fields or text indexes (backfill and/or re-embed/rebuild), so retrieval data_scope and hybrid search are not silently incomplete.

#### Scenario: Migration guidance exists
- **WHEN** upgrading an environment that already has prod vectors
- **THEN** operators have a defined backfill or rebuild procedure

### Requirement: Promote is invoked only through eval orchestration
The system SHALL expose an internal/facade `promote(embedding_task_id)` for promoting a completed canary embedding task to prod (Milvus + MySQL release_tag switch as today). The system MUST NOT provide a content-side standalone manual publish UI/API for operators in this change. Promote SHALL be intended for `knowledge-admin` eval-task orchestration only.

#### Scenario: Facade promote switches canary to prod
- **WHEN** admin calls promote for a valid COMPLETED canary embedding task
- **THEN** the task's segments/vectors become prod and prior prod for that doc is demoted per existing publish semantics

### Requirement: No automatic canary promote
The system MUST NOT automatically promote completed canary embedding tasks to prod on a schedule or background job. Existing auto-promote code paths and job registrations SHALL be deleted.

#### Scenario: Completed canary stays canary until eval publish
- **WHEN** an embedding task completes successfully as canary
- **THEN** it remains canary until promote is invoked via eval-task orchestration

### Requirement: Segment and embedding-task query for eval
The system SHALL expose internal/facade APIs to query embedding tasks (for binding COMPLETED canary tasks) and to list/get/search document segments (shared with MCP) filtered by `doc_id` and optional `release_tag`/`task_id`.

#### Scenario: List completed canary tasks for binding
- **WHEN** admin requests embedding tasks eligible for eval binding
- **THEN** the system can return COMPLETED tasks that are still canary for selection
