## ADDED Requirements

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
