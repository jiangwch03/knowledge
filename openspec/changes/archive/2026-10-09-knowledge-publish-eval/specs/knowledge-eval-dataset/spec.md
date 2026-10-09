## ADDED Requirements

### Requirement: Dataset is scoped to one document
The system SHALL allow creating an evaluation dataset with a business name and exactly one `doc_id`. Multiple datasets MAY exist for the same `doc_id`, distinguished by name. Datasets MUST be independent of the split/embedding pipeline and reusable across eval tasks.

#### Scenario: Create dataset for one doc
- **WHEN** an authorized user creates a dataset with a name and one document
- **THEN** the system persists the dataset bound to that `doc_id` only

#### Scenario: Same doc multiple datasets
- **WHEN** a user creates a second dataset for the same `doc_id` with a different name
- **THEN** the system accepts it as a separate reusable dataset

### Requirement: Questions come only from one generation run
Creating a dataset SHALL start the generation Agent for a single run that writes items. The system MUST NOT provide a blank-item manual entry path. The system MUST NOT support incremental re-generation or appending new items to an existing dataset in this change. Humans MAY edit existing items' question, ground truth, reference excerpts, and `enabled` flag only.

#### Scenario: New dataset triggers generation
- **WHEN** a user creates a dataset with doc and name
- **THEN** the system starts the generation Agent once and persists generated items

#### Scenario: Human edits existing item
- **WHEN** a user updates an existing dataset item's question or ground truth
- **THEN** the system saves the edits without requiring re-generation

#### Scenario: Manual add and top-up forbidden
- **WHEN** a client attempts to create a blank item or start incremental generation on an existing dataset
- **THEN** the system rejects the request

### Requirement: Generation Agent uses segment MCP with hard-coded quota
The generation Agent SHALL call segment MCP tools (`list` then selective `get`/`search`) and MUST NOT load the full document by default. The system prompt SHALL hard-code a target of **20–40** questions with difficulty ratio simple:medium:hard = **1:2:1**. Hard questions MUST synthesize information from at least two sources/segments. Each item SHALL store reference excerpts and MAY store `used_chunk_ids` for provenance. If budget is exceeded, the Agent MAY produce fewer than 20 questions but SHOULD preserve the 1:2:1 ratio as far as possible.

#### Scenario: Quota written in prompt
- **WHEN** the generation Agent runs
- **THEN** its instructions require 20–40 items at 1:2:1 difficulty mix

#### Scenario: Agent lists before bulk get
- **WHEN** the generation Agent starts reading segments
- **THEN** it lists segment directory/previews first and only then fetches selected full texts within budget

#### Scenario: Hard item needs multi-segment evidence
- **WHEN** the Agent emits a hard-difficulty item
- **THEN** the item references at least two distinct evidence sources (excerpts and/or chunk ids)

### Requirement: Dataset tables owned by admin in shared DB
The system SHALL store datasets and items in `knowledge_eval_dataset` and `knowledge_eval_dataset_item` in the same database as existing `knowledge_*` tables, maintained by `knowledge-admin`.

#### Scenario: Persist generated items
- **WHEN** generation completes successfully
- **THEN** items are written to `knowledge_eval_dataset_item` under the dataset id
