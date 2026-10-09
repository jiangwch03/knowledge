## ADDED Requirements

### Requirement: Topic records are managed under knowledge admin
The system SHALL provide a 主题管理 menu under 知识管理. Operators SHALL create, list, view, update, and soft-delete topics. A topic MUST have a unique name among rows with `del_flag='0'`. Soft-deleted names MAY be reused.

#### Scenario: Create topic with a unique name
- **WHEN** an operator submits a new topic whose trimmed name is non-empty, at most 64 characters, and not used by another active topic
- **THEN** the system stores the topic with `del_flag='0'` and returns it

#### Scenario: Reject duplicate active name
- **WHEN** an operator submits a topic name that already belongs to an active topic
- **THEN** the system rejects the request and does not create a second active topic

#### Scenario: Soft-delete topic and its keywords
- **WHEN** an operator deletes a topic
- **THEN** the topic and its keywords are marked deleted (`del_flag='2'`) and no longer appear in lists or routing

### Requirement: Creating a topic generates keywords from one completed split task
Creating a topic MUST require a topic name and one embedding task whose status is `COMPLETED`. The system MUST generate keywords with `jieba.analyse.extract_tags` (`topK` unset so every tag is kept, `withWeight=True`, `allowPOS` nouns and English) from that task's source segments. Source segments MUST be parent chunks (`skip_embedding=1`) and standalone chunks whose `parent_chunk_id` is empty. Child chunks that point at a parent MUST NOT be used. Duplicate keywords MUST keep the higher weight. The stored set MUST NOT be truncated by a keyword count. Saving MUST persist the topic as `GENERATING` and return without waiting for extraction. A consumer MUST then extract keywords and set the topic to `READY`, or to `FAILED` with an error message when extraction is empty or errors. Generation MUST NOT add a stage to the embedding task state machine. A second update MUST be rejected while status is `GENERATING`. A failed topic MUST be retryable without changing the split task or the saved keep-or-clear choice.

#### Scenario: Parent text is used when a section was split
- **WHEN** the selected task contains a parent chunk and child chunks for the same section
- **THEN** keyword extraction reads the parent text and does not read the child texts

#### Scenario: Standalone chunk is used when there is no parent
- **WHEN** a segment has no parent chunk id
- **THEN** keyword extraction reads that segment's own text

#### Scenario: Every extracted keyword is stored
- **WHEN** extraction produces many distinct keywords
- **THEN** the topic stores all of them, ordered by weight, with no count cutoff

#### Scenario: Incomplete task is rejected
- **WHEN** the selected embedding task is missing, deleted, or not `COMPLETED`
- **THEN** the system rejects topic creation

### Requirement: Updating a topic keeps the name and lets the operator choose keyword retention
An update MUST NOT change `topic_name`. The operator MUST be able to change the split task. The update MUST require an explicit choice to clear or keep existing keywords. Clearing MUST replace keywords with a fresh extraction from the selected task. Keeping MUST merge old and new keywords by term and retain the higher weight for the same term. Neither choice truncates the stored set by a keyword count.

#### Scenario: Name is unchanged on update
- **WHEN** an operator updates a topic
- **THEN** the stored topic name remains the original name

#### Scenario: Operator clears old keywords
- **WHEN** an operator updates the split task and chooses to clear old keywords
- **THEN** previous keywords are soft-deleted and only the new extraction remains active

#### Scenario: Operator keeps old keywords
- **WHEN** an operator updates the split task and chooses to keep old keywords
- **THEN** the active set is the weight-merged union of old and new keywords

### Requirement: Topic and keyword data live in dedicated tables
The system MUST persist topics in `knowledge_retrieve_topic` and keywords in `knowledge_retrieve_topic_keyword` in the same database as other `knowledge_*` tables. Keyword rows MUST store the term and its extraction weight. Business APIs MUST pass topics and keywords as typed models, not untyped dictionaries.

#### Scenario: List shows task and keyword count
- **WHEN** an operator opens the topic list
- **THEN** each active topic shows its name, the split task as document title plus task id, generation status, and current keyword count
