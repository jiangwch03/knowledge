## ADDED Requirements

### Requirement: Uploaded markdown is split into sections without persisting segments
The system SHALL expose `GET /internal/documents/{docId}/sections` for a document's parsed Markdown. The system MUST split by ATX headings and MUST NOT treat a `#` inside a fenced code block as a heading. When the markdown has no headings, the system MUST split into sections of about 8000 characters. Each section MUST include a zero-based order, a title, a parent title, and the section body. A character-split section MUST have an empty title. A section with no parent heading MUST have an empty parent title. The system MUST NOT write these sections into the embedding segment table and MUST NOT cut them again by embedding chunk size.

#### Scenario: Heading split returns parent title
- **WHEN** an uploaded markdown contains a level-1 heading and two level-2 headings under it
- **THEN** the level-2 sections are returned in order with that level-1 text as parent title and their own heading text as title

#### Scenario: Code fence hash is not a heading
- **WHEN** a fenced code block contains a line that starts with `#`
- **THEN** that line stays inside the surrounding section body and does not start a new section

#### Scenario: No headings uses character sections
- **WHEN** the markdown has no ATX headings and is longer than 8000 characters
- **THEN** the system returns multiple sections with empty title and empty parent title

#### Scenario: Sections are not stored as embedding segments
- **WHEN** the sections endpoint is called
- **THEN** the response contains the section list and no new rows are written to the embedding segment table
