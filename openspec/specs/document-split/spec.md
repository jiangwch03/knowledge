## Purpose

规范文档切分策略目录、同步预览、分段持久化（含父子元数据）以及切分成功后的文档状态推进。

## Requirements

### Requirement: Five split strategies are available
The system SHALL support TITLE, LENGTH, SEPARATOR, REGEX, and SMART with the parameter rules in the product requirements.

#### Scenario: Strategy metadata for configuration UI
- **WHEN** a client requests the split strategy catalog
- **THEN** the system returns each strategy code, name, description, notes, and parameter schema

### Requirement: Synchronous split preview without persistence
The system SHALL provide a synchronous preview that splits a Markdown sample without writing segments, calling embedding, or writing Milvus.

#### Scenario: Crawl preview defaults to first file
- **WHEN** a user previews split for a crawl document without fileId
- **THEN** the system uses the first knowledge_document_file ordered by id ascending

### Requirement: Segments persist with parent-child metadata for TITLE and SMART
The system SHALL persist split results including release_tag, and for TITLE/SMART oversize sections SHALL create parent segments with skip_embedding=1.

#### Scenario: Parent segment skips embedding flag
- **WHEN** TITLE or SMART produces a parent segment for an oversize section
- **THEN** the parent is stored with skip_embedding=1

### Requirement: Document status advances to CHUNKED after split
The system SHALL set knowledge_document.status to CHUNKED after successful full-document split persistence.

#### Scenario: Successful split updates document status
- **WHEN** all files are split and segments saved
- **THEN** the document status becomes CHUNKED
