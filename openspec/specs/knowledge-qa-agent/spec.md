## Purpose

规范知识问答 Agent：单图内改写与话题路由、复用 common 会话/SSE 运行时、可选 Tavily、流式引用与聊天权限。

## Requirements

### Requirement: Single Agent graph with internal rewrite and topic routing
The knowledge QA path SHALL use a **single** Agent graph and a single session `agent_type`. Query rewrite and topic routing SHALL run as **Agent middleware** (inside the graph) and decide (1) which system prompt profile to load (customer-service vs knowledge-QA) and (2) whether hybrid retrieve middleware runs for this turn (`need_retrieve`). Turn-scoped routing/retrieve state MUST be reset at the start of each user turn so checkpointer history does not reuse the previous turn's gate decision.

#### Scenario: Related topic runs retrieve middleware
- **WHEN** topic routing middleware marks the question as related to dictionary topics
- **THEN** the Agent turn uses the knowledge-QA prompt profile and runs hybrid retrieve middleware before generation

#### Scenario: Unrelated topic skips retrieve
- **WHEN** topic routing middleware marks the question as unrelated
- **THEN** the Agent turn uses the customer-service prompt profile, MUST NOT run hybrid knowledge retrieve, and MUST NOT emit fake knowledge-base citations

### Requirement: Topic list from system dictionary
Topic options SHALL come from a system dictionary (seeded with `milvus`, `ai_production`, `langchain`, `langgraph`). Upload/crawl flows are NOT required to tag documents with topics in this change.

#### Scenario: Dictionary drives routing labels
- **WHEN** topic routing runs
- **THEN** it compares the user question against the configured dictionary topic list

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
