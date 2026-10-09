## Purpose

规范知识问答 Agent：单图内改写与话题路由、复用 common 会话/SSE 运行时、可选 Tavily、流式引用与聊天权限。

## Requirements

### Requirement: Single Agent graph with internal rewrite and topic routing
The knowledge QA path SHALL use a **single** Agent graph and a single session `agent_type`. Query rewrite and topic routing SHALL run as **Agent middleware** (inside the graph) and decide (1) which system prompt profile to load (customer-service vs knowledge-QA) and (2) whether hybrid retrieve middleware runs for this turn (`need_retrieve`). Turn-scoped routing/retrieve state MUST be reset at the start of each user turn so checkpointer history does not reuse the previous turn's gate decision.

#### Scenario: Related topic runs retrieve middleware
- **WHEN** topic routing middleware marks the question as related, either by a managed-topic keyword hit or by the topic model
- **THEN** the Agent turn uses the knowledge-QA prompt profile and runs hybrid retrieve middleware before generation

#### Scenario: Unrelated topic skips retrieve
- **WHEN** topic routing middleware marks the question as unrelated
- **THEN** the Agent turn uses the customer-service prompt profile, MUST NOT run hybrid knowledge retrieve, and MUST NOT emit fake knowledge-base citations

### Requirement: Reuse Agent session and SSE runtime
Session CRUD, message persistence, and SSE event-stream handling MUST reuse `knowledge-common` Agent base (`AgentSessionService`, `AgentChatService` / stream processor). The retrieval package MUST NOT reimplement these from scratch. Controllers MAY be thin wrappers analogous to the web crawler Agent APIs.

#### Scenario: Multi-turn history via existing tables
- **WHEN** a user chats in a knowledge QA session
- **THEN** messages are stored in `knowledge_agent_session` / `knowledge_agent_message` with the knowledge QA `agent_type`

### Requirement: Optional Tavily tool
The Agent SHALL expose a Tavily web search tool that the model may invoke to supplement answers. Tavily API key SHALL be read from system config `rag.tavily.api_key`. Initialization SQL MUST NOT contain a real key (empty/placeholder only). Web results MUST be distinguishable from knowledge-base citations.

#### Scenario: Missing Tavily key degrades
- **WHEN** the config key is empty or placeholder
- **THEN** the Agent can still answer without web search (tool unavailable or friendly failure) without aborting the session

#### Scenario: Unrelated turn may still use Tavily
- **WHEN** the turn is unrelated to knowledge topics
- **THEN** the customer-service Agent MAY call Tavily but MUST NOT label web content as imported knowledge-base citations

### Requirement: Streaming answer with citations
The chat message API SHALL stream SSE (or the project's Agent stream protocol). When knowledge hits exist, citation metadata SHALL include at least doc/chunk identifiers consistent with parent-expansion fields.

#### Scenario: Grounded answer includes citations
- **WHEN** hybrid retrieve returns hits and generation completes
- **THEN** the client receives citation metadata for knowledge hits

### Requirement: Chat permission
Knowledge QA chat APIs SHALL require `rag:retrieve:chat` (or equivalent).

#### Scenario: Unauthorized chat blocked
- **WHEN** a caller without chat permission sends a message
- **THEN** the request is denied

### Requirement: No dual-agent graphs per session
The system MUST NOT switch between two different compiled graphs per turn for CS vs QA in a way that shares conflicting checkpointer state. Prompt profile switching inside one graph/middleware is required instead.

#### Scenario: One thread id per session
- **WHEN** consecutive turns alternate related and unrelated
- **THEN** they still use one session id / agent_type and one Agent graph definition

### Requirement: Agent retrieve respects releaseTag and taskId
The knowledge QA Agent path SHALL accept optional `releaseTag` and `taskId` (default `releaseTag=prod`) and pass them into hybrid retrieve so evaluation can target canary vectors for a specific embedding task. Online chat without these parameters MUST continue to retrieve prod.

#### Scenario: Default online chat uses prod
- **WHEN** a user sends a normal chat message without release/task overrides
- **THEN** hybrid retrieve filters with release_tag=prod

#### Scenario: Eval canary with task id
- **WHEN** an eval caller invokes the Agent or eval API with releaseTag=canary and a taskId
- **THEN** hybrid retrieve filters with that release_tag and task_id

### Requirement: Non-streaming eval exit returns answer and contexts
The system SHALL expose a non-streaming facade/API for evaluation that, given a question plus release/task context, returns `{answer, contexts}` suitable for Ragas offline scoring. This exit MUST NOT require SSE consumption by the admin batch runner.

#### Scenario: Eval batch collects answer and contexts
- **WHEN** admin runs an evaluation item against the eval API with canary+taskId
- **THEN** the response includes the model answer and the retrieved contexts used for that answer

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
