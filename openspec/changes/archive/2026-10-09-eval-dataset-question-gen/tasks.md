## 1. Content section split

- [x] 1.1 Add section VO and a pure markdown section splitter (headings, code fences, 8000-char fallback)
- [x] 1.2 Expose `GET /internal/documents/{docId}/sections` that reads parsed markdown and returns sections without writing the segment table
- [x] 1.3 Unit-test heading split, code-fence hashes, parent title, and the no-heading character split

## 2. Admin material plan

- [x] 2.1 Add quota split 4:2:2:1:1 with remainder to simple questions
- [x] 2.2 Add crawl systematic sample, navigation-link drop, and one-link pairing capped at 20 pages
- [x] 2.3 Add upload sibling-section pairing and the small-batch versus large-batch plan
- [x] 2.4 Unit-test quota, endpoint inclusion, navigation drop, and forward walk

## 3. Generation wiring

- [x] 3.1 Add the admin sections RPC client
- [x] 3.2 Call RAGAS with the batch-specific query distribution; keep a failed multi-hop batch at zero
- [x] 3.3 Generate vague, adversarial, and comprehensive questions from the custom batch, with adversarial ground truth `不知道`
- [x] 3.4 Persist the mixed items through the existing dataset generation run
