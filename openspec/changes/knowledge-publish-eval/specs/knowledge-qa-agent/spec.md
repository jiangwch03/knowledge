## ADDED Requirements

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
