## Purpose

规范认证混合检索 HTTP API：dense+BM25 融合、release_tag/taskId、TopK 阈值、父段展开、data_scope 过滤与权限。

## Requirements

### Requirement: Authenticated hybrid search API
The system SHALL provide an authenticated HTTP API that accepts a natural-language query, runs **hybrid retrieval** (dense vector ANN + keyword/full-text over stored `text`), fuses results (RRF or equivalent), and returns ranked hits.

#### Scenario: Default prod hybrid search returns hits
- **WHEN** an authorized caller submits a non-empty query with default parameters
- **THEN** the system embeds the query, searches with filter including `release_tag == "prod"` and the caller's data_scope constraints, fuses vector and text channels, and returns up to `top_k` hits

#### Scenario: Empty query rejected
- **WHEN** the caller submits an empty or whitespace-only query
- **THEN** the system rejects the request with a validation error and does not call Milvus

### Requirement: Release tag and optional taskId
The system SHALL default `releaseTag` to `prod`, ALLOW explicit `releaseTag` override, and ALLOW optional `taskId` for debugging and RAGAS validation (OpenAPI/description MUST state this purpose). The system MUST NOT implement traffic-percentage canary routing.

#### Scenario: Canary and task pin for evaluation
- **WHEN** an authorized caller sets `releaseTag=canary` and optionally `taskId`
- **THEN** Milvus filters honor those constraints for both vector and text channels

### Requirement: TopK and score threshold
The system SHALL default `top_k=5` and `score_threshold=0.5` (overridable). `score_threshold` MUST constrain the **dense vector** channel as a COSINE range-search lower bound (Milvus `radius`); it MUST NOT filter fused RRF scores or rerank scores. The public score field MUST be larger-is-better.

#### Scenario: Threshold limits weak dense candidates
- **WHEN** an authorized caller sets `score_threshold=0.5`
- **THEN** the dense ANN sub-request uses COSINE range search with `radius=0.5`, while BM25/RRF fusion and optional rerank do not re-apply that threshold as a post-fusion score cut

### Requirement: Hybrid search uses Milvus native fusion
The system SHALL run dense ANN and BM25 sparse search via Milvus `hybrid_search` with server-side RRF (`RRFRanker`). The system MUST NOT implement application-level dual-search RRF fusion, and MUST NOT soft-degrade to vector-only when the hybrid request fails (treat as a normal retrieval error).

#### Scenario: Native hybrid returns ranked hits
- **WHEN** an authorized caller submits a non-empty query
- **THEN** the system embeds the query, invokes one Milvus `hybrid_search` under release_tag and data_scope filters, and returns up to `top_k` hits (after optional rerank and parent expansion)

### Requirement: Parent segment expansion fields
When parent expansion applies, the system SHALL replace hit `text` with parent full text, set `chunkId` to the parent chunk id, set `hitChunkId` to the child hit chunk id, and set `expandedFromChild=true`. When no expansion occurs, `expandedFromChild=false` and ids may be equal.

#### Scenario: Child hit expanded
- **WHEN** a hit maps to a child segment with `parent_chunk_id` and expansion is enabled
- **THEN** response text is parent content and expansion fields are populated as specified

### Requirement: Vector-side data scope filtering
The system SHALL apply data_scope-equivalent filters on Milvus using redundant `dept_id` and `user_id` fields so unauthorized documents are not returned as hits.

#### Scenario: Out-of-scope docs excluded
- **WHEN** vectors exist for documents outside the caller's data scope
- **THEN** those vectors are not returned in search hits

### Requirement: Empty retrieval is success with empty list
When no qualifying hits remain, the system SHALL return HTTP success with an empty hit list.

#### Scenario: No matching vectors
- **WHEN** search completes with zero qualifying hits
- **THEN** the response contains zero hits and is not a 5xx

### Requirement: Retrieve permission
The search API SHALL require interface permission `rag:retrieve:query` (or equivalent seeded permission).

#### Scenario: Unauthorized caller blocked
- **WHEN** a caller without the retrieve permission invokes the search API
- **THEN** the request is denied by the auth layer
