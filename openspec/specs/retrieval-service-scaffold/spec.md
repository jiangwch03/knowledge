## Purpose

规范 `knowledge-retrieval` 独立服务脚手架：workspace 包布局、FastAPI 路由注册、默认 lifespan 不挂载 embedding 消费与调度。

## Requirements

### Requirement: Workspace package knowledge-retrieval exists
The system SHALL provide a uv workspace member package `knowledge-retrieval` depending on `knowledge-common`, startable as an independent FastAPI process, following the same packaging layout as `knowledge-content`.

#### Scenario: Package is a workspace member
- **WHEN** the root workspace is synced
- **THEN** `knowledge-retrieval` is listed as a workspace member and installs with dependency `knowledge-common`

#### Scenario: Process starts with isolated app identity
- **WHEN** the retrieval service is started with its env config
- **THEN** `app_name` identifies the retrieval app and `app_port` defaults to `9101` (overridable by env)

### Requirement: FastAPI app registers retrieval and QA routes
The system SHALL expose a FastAPI application that registers retrieval/session/chat controllers via shared router auto-registration and the shared middleware/auth stack from `knowledge-common`.

#### Scenario: Docs reachable after start
- **WHEN** the retrieval service starts successfully
- **THEN** the HTTP server listens on the configured host/port and OpenAPI docs are available unless disabled by config

### Requirement: No embedding consumers on retrieval lifespan
The retrieval service MUST NOT register or start `embedding.pending` (or other knowledge-content ingest) message consumers in its default lifespan.

#### Scenario: Lifespan excludes ingest consumers
- **WHEN** the retrieval application lifespan initializes
- **THEN** it does not start embedding pipeline consumers that belong to `knowledge-content`

### Requirement: Zero new retrieval schedulers and consumers
The knowledge-retrieval package SHALL NOT introduce new message consumers or recurring scheduled jobs for the QA/retrieve path (one-off migration scripts are allowed outside the consumer framework).

#### Scenario: No QA queue consumer
- **WHEN** operators inspect retrieval process registrations
- **THEN** there is no MQ consumer required for answering a user chat message
