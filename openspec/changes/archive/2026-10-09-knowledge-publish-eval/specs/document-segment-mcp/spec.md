## ADDED Requirements

### Requirement: List document segments without full text
The system SHALL expose an MCP tool `list_document_segments` that, given `doc_id` and optional `release_tag`/`task_id`, returns segment directory entries with identifiers, order, title or short preview, and length, and MUST NOT return full segment bodies.

#### Scenario: List returns previews only
- **WHEN** the generation Agent calls `list_document_segments` for a document
- **THEN** the response includes ordered segment metadata/previews without full text

### Requirement: Get selected segment bodies with batch limit
The system SHALL expose `get_document_segments` that returns full text for a caller-specified list of segment/chunk ids under a per-call maximum K, scoped to the given document (and optional release/task filter).

#### Scenario: Batch get respects K
- **WHEN** the caller requests more than K segment ids in one get
- **THEN** the system rejects or truncates according to the configured K limit and does not return unbounded bodies

### Requirement: Search segments within one document
The system SHALL expose `search_document_segments` that, given `doc_id` and a query plus optional release/task filter, returns relevant segment previews or bodies for gap-filling within that document only.

#### Scenario: Search scoped to one doc
- **WHEN** the Agent searches with a query for a doc_id
- **THEN** results are limited to segments of that document (and the specified release/task version when provided)

### Requirement: Segment tools share content query implementation
MCP segment tools SHALL be backed by `knowledge-content` segment query logic and MAY share the same implementation with internal HTTP/RPC facades used by non-Agent callers.

#### Scenario: Same data for MCP and facade
- **WHEN** the same doc_id and task_id are queried via MCP list and via the content segment query facade
- **THEN** both surfaces return consistent segment membership for that version
