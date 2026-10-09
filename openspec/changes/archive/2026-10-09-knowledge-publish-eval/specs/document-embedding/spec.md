## ADDED Requirements

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
