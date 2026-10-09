## MODIFIED Requirements

### Requirement: Single Agent graph with internal rewrite and topic routing
The knowledge QA path SHALL use a **single** Agent graph and a single session `agent_type`. Query rewrite and topic routing SHALL run as **Agent middleware** (inside the graph) and decide (1) which system prompt profile to load (customer-service vs knowledge-QA) and (2) whether hybrid retrieve middleware runs for this turn (`need_retrieve`). Turn-scoped routing/retrieve state MUST be reset at the start of each user turn so checkpointer history does not reuse the previous turn's gate decision.

#### Scenario: Related topic runs retrieve middleware
- **WHEN** topic routing middleware marks the question as related, either by a managed-topic keyword hit or by the topic model
- **THEN** the Agent turn uses the knowledge-QA prompt profile and runs hybrid retrieve middleware before generation

#### Scenario: Unrelated topic skips retrieve
- **WHEN** topic routing middleware marks the question as unrelated
- **THEN** the Agent turn uses the customer-service prompt profile, MUST NOT run hybrid knowledge retrieve, and MUST NOT emit fake knowledge-base citations

## REMOVED Requirements

### Requirement: Topic list from system dictionary
**Reason**: Topic names and domain keywords are maintained as topic records. The dictionary cannot store a split task, a keyword limit, or the extracted terms.
**Migration**: Create topics in 主题管理 and bind a completed split task. While no active topic exists, routing still reads `rag_retrieve_topic`. After the first active topic exists, the dictionary is not used.

## ADDED Requirements

### Requirement: Topic routing matches managed keywords before the topic model
When at least one topic with status `READY` exists, topic routing MUST load those topic names, descriptions, and keywords from `knowledge_retrieve_topic` and `knowledge_retrieve_topic_keyword`. Topics that are `GENERATING` or `FAILED` MUST NOT participate. The question MUST be segmented with jieba. If any token matches an active keyword, case-insensitively, routing MUST set the knowledge prompt profile and MUST NOT call the topic-gate model. If no keyword matches, routing MUST call the existing topic-gate model with each active topic name and its description as `{topics}`. When no active topic exists, routing MUST continue to use the `rag_retrieve_topic` dictionary. Managed keywords MUST NOT be written into the Milvus sparse field and MUST NOT replace the query text sent to hybrid retrieve.

#### Scenario: Keyword hit skips the topic model
- **WHEN** an active topic has the keyword 分析器 and the user question segments to a token 分析器
- **THEN** routing selects the knowledge profile and does not call the topic-gate model

#### Scenario: Miss falls through to the topic model
- **WHEN** active topics exist and no jieba token of the question is in the keyword table
- **THEN** routing asks the topic-gate model using each active topic name and its description

#### Scenario: Empty topic table keeps dictionary routing
- **WHEN** there is no active topic
- **THEN** routing compares the question with the `rag_retrieve_topic` dictionary labels
