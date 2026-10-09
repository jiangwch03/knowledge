## ADDED Requirements

### Requirement: Eval task binds dataset and embedding task
The system SHALL allow creating an eval task that binds a reusable evaluation dataset and a completed canary embedding task for the same document. Before archive, the user MAY change the bound dataset. The task status SHALL be `OPEN` or `ARCHIVED`.

#### Scenario: Create open eval task
- **WHEN** an authorized user selects a dataset and a COMPLETED canary embedding task for the same doc
- **THEN** the system creates an `OPEN` eval task linking both

#### Scenario: Swap dataset while open
- **WHEN** the task is `OPEN` and the user changes `dataset_id`
- **THEN** the system updates the current dataset binding without deleting past runs

### Requirement: Multiple read-only evaluation runs
The system SHALL allow running evaluation multiple times on an `OPEN` task. Each run SHALL snapshot enabled questions, call the retrieval eval API with `release_tag=canary` and the bound `task_id`, compute Ragas metrics asynchronously in admin, and persist full results on `knowledge_eval_run` / `knowledge_eval_run_item`. Runs MUST be append-only for business fields (status may move PENDING→RUNNING→SUCCESS/FAILED only). Failed runs MUST leave the task `OPEN`.

#### Scenario: Successful run persists metrics
- **WHEN** a run finishes Ragas scoring without error
- **THEN** the run status is SUCCESS and summary plus per-item metrics are stored

#### Scenario: Failed run stays open
- **WHEN** a run fails mid-batch
- **THEN** the run is FAILED with an error message and the eval task remains OPEN for retry

### Requirement: Publish only via eval task with historical SUCCESS
The system SHALL allow publishing only from an `OPEN` eval task that has at least one historical run with status SUCCESS (any dataset binding in that task's history). Changing the dataset MUST NOT invalidate prior SUCCESS runs for this gate. Publishing SHALL call content `promote(embedding_task_id)` and on success set the eval task to `ARCHIVED` with `publish_time`. ARCHIVED tasks MUST reject dataset change, re-run, and re-publish; reports remain readable.

#### Scenario: Publish blocked without success run
- **WHEN** an OPEN task has no SUCCESS run
- **THEN** the system rejects publish

#### Scenario: Publish after success even if dataset swapped
- **WHEN** an OPEN task had a SUCCESS run then the dataset was changed without a new run
- **THEN** the system still allows publish (historical SUCCESS counts)

#### Scenario: Successful promote archives task
- **WHEN** promote succeeds for the bound embedding task
- **THEN** the eval task becomes ARCHIVED and further mutate operations are rejected

#### Scenario: Archived reports remain readable
- **WHEN** a user opens reports for an ARCHIVED task
- **THEN** past runs and metrics are available read-only

### Requirement: No automatic score gate
Ragas scores and reference thresholds MAY be shown to humans but MUST NOT automatically block or approve promote.

#### Scenario: Low scores still allow human publish
- **WHEN** a SUCCESS run has metrics below reference lines and the historical SUCCESS gate is met
- **THEN** an authorized user may still click publish (scores are advisory only)

### Requirement: Eval task tables owned by admin in shared DB
The system SHALL store tasks, runs, and run items in `knowledge_eval_task`, `knowledge_eval_run`, and `knowledge_eval_run_item` in the shared `knowledge_*` database, maintained by `knowledge-admin`.

#### Scenario: Run items snapshot questions
- **WHEN** a run starts
- **THEN** each run item stores snapshotted question, ground truth, and reference excerpts independent of later dataset edits
