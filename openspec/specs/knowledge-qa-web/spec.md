## Purpose

规范 knowledge-web 侧知识问答菜单与聊天页，以及对接 `knowledge-retrieval` 会话/聊天 API。

## Requirements

### Requirement: Knowledge QA menu and chat page
The system SHALL add a knowledge-web menu and chat page for knowledge QA, modeled after the web-crawler agent session UX (session list, history messages, send message with streaming).

#### Scenario: User opens knowledge QA page
- **WHEN** an authorized user opens the knowledge QA menu entry
- **THEN** they can create/select a session and send messages that stream Agent responses

### Requirement: Frontend calls retrieval service APIs
The page SHALL call `knowledge-retrieval` session/chat APIs (not `knowledge-admin` AiChatService for this feature).

#### Scenario: History reload
- **WHEN** the user reopens a session
- **THEN** prior messages are loaded from the session messages API and displayed
