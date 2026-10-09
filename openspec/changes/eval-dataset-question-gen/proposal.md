## Why

测评集出题现在把整篇文档的原文一次交给 RAGAS，题型由默认合成器平分，没有先把页圈小。页数一多，时间几乎全耗在出题前的预处理上，而且出不了「问法不清」「文档里没有、应回答不知道」和「对一大段做总结」这三类题。圈资料和四类题的出法已经定稿，见 `docs/rag/测试集出题架构方案.md`。

## What Changes

- **BREAKING**（相对进行中的 `knowledge-publish-eval` 出题要求）：不再用生成 Agent + 分段 MCP、不再按 20～40 题和简单:中等:高难 = 1:2:1 出题。出题改为本地圈资料，再分题型生成。
- 圈资料在本地完成，不调用模型。爬取按子网页个数、上传按切出来的节数，小于等于 20 全部投喂；大于 20 才抽样。MMR 不进主路径。
- 简单题、多跳用 RAGAS，并传入 `query_distribution`。大于 20 时简单题和多跳分成两次调用，各带各的材料。多跳建不出关系时这批为 0，不退回简单题合成器。
- 模糊题、对抗题、综合题自己写。对抗题标准答案是「不知道」。这三类不再另圈材料。
- 题数沿用创建时的 `question_count`（至少 50），按 4:2:2:1:1 分成简单、多跳、综合、模糊、对抗，余数补给简单题。
- content 新增上传文档切节对内接口。不改现有分段接口，不把向量分段交给出题。

## Capabilities

### New Capabilities

- `eval-question-generation`: 按爬取或上传圈资料，RAGAS 出简单题和多跳，自写模糊、对抗、综合题，并写入测评集。
- `document-eval-sections`: 上传文档按标题（无标题则按字数）切成出题用的节，只返回、不落分段表。

### Modified Capabilities

- 无。主规格里还没有测评集出题；`document-split` 仍只服务向量分段，本变更不改它的要求。

## Impact

- **服务**：`knowledge-admin` 改出题编排；`knowledge-content` 增加切节对内接口。打分、测评任务、发布仍走 `knowledge-publish-eval`，不改。
- **接口**：新增 `GET /internal/documents/{docId}/sections`。爬取继续用已有 `/internal/documents/{docId}/source-files`。
- **依赖**：继续用 RAGAS 出题和打分。LlamaIndex、DeepEval 不参与出题。
- **进行中的变更**：`knowledge-publish-eval` 里「生成 Agent + 分段 MCP」的出题要求由本变更取代，不再按那条实现。
