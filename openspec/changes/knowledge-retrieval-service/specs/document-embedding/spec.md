## ADDED Requirements

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
