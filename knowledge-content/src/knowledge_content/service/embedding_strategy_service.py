from copy import deepcopy

from knowledge_common.service.rag_config_service import RagConfigService
from knowledge_content.enums.document_split_regex_template_dict_enum import DocumentSplitRegexTemplateDict
from knowledge_content.enums.document_split_separator_dict_enum import DocumentSplitSeparatorDict
from knowledge_content.enums.split_type_enum import SplitType
from knowledge_content.vo.embedding_vo import EmbeddingStrategyVo


class EmbeddingStrategyService:
    """切分策略静态元数据（与产品文档对齐；name 来自 SplitType.label）"""

    _STRATEGIES: list[EmbeddingStrategyVo] = [
        EmbeddingStrategyVo(
            code=SplitType.TITLE.value,
            name=SplitType.TITLE.label,
            summary='按你指定的 Markdown 标题层级把文章切成章节段；某一段太长时再二次切成子块。',
            process_steps=[
                '从上到下按行读文章；遇到不超过「标题层级」的标题（如层级=2 则识别 # / ##）时，在标题处切开，开启新段。',
                '同一标题下的连续正文行合并成一整段，并带上当前标题路径（一级/二级/…）。',
                '代码块（``` / ~~~）里的 # 不当标题，整段代码跟正文一起走。',
                '若某段长度 ≤ 块大小：整段作为一块写入向量库。',
                '若某段长度 > 块大小：先保留整段作为父片（不入向量库），再按块大小滑动切出多个子片（相邻子片重叠「重叠长度」字符），只把子片写入向量库。',
            ],
            applicable_scenes=['技术文档', '手册', '带清晰章节结构的 Markdown'],
            notes=[
                '标题与标题之间切开的普通块互不重叠；重叠只发生在超长段硬切出的子块之间',
                '超长父片 skipEmbedding，仅子片写入向量库',
            ],
            param_notes=[
                '标题层级：参与切分的最大 Markdown 标题级别（1–6，对应 # ~ ######）',
                '块大小：单段超过该长度才做父子二次切分；子块最长不超过该值；上限对齐精排单文档字符上限',
                '重叠长度：仅在超长段切出的子块之间生效',
            ],
            param_schema={
                'type': 'object',
                'required': ['splitType', 'chunkSize', 'titleLevel'],
                'properties': {
                    'splitType': {'const': 'TITLE'},
                    'chunkSize': {'type': 'integer', 'minimum': 1},
                    'titleLevel': {'type': 'integer', 'minimum': 1, 'maximum': 6},
                    'overlap': {'type': 'integer', 'minimum': 0},
                },
            },
        ),
        EmbeddingStrategyVo(
            code=SplitType.LENGTH.value,
            name=SplitType.LENGTH.label,
            summary='不看标题结构，把全文按目标长度切成连续块；相邻块可重叠。',
            process_steps=[
                '忽略 Markdown 标题，把全文当作纯文本处理。',
                '优先在段落/换行等空白边界处切开，尽量凑满「块大小」。',
                '若某个词或片段本身仍超过块大小，再按字符硬切。',
                '相邻块之间保留「重叠长度」字符的重叠，避免句子被拦腰切断后丢上下文。',
            ],
            applicable_scenes=['纯文本', '结构弱的长文档'],
            notes=['无标题元数据；适合结构弱、没有可靠标题边界的文档'],
            param_notes=[
                '块大小：目标分块最大字符数；上限对齐精排单文档字符上限',
                '重叠长度：相邻分块之间的重叠字符数（须小于块大小）',
            ],
            param_schema={
                'type': 'object',
                'required': ['splitType', 'chunkSize'],
                'properties': {
                    'splitType': {'const': 'LENGTH'},
                    'chunkSize': {'type': 'integer', 'minimum': 1},
                    'overlap': {'type': 'integer', 'minimum': 0},
                },
            },
        ),
        EmbeddingStrategyVo(
            code=SplitType.SEPARATOR.value,
            name=SplitType.SEPARATOR.label,
            summary='先按所选分隔符拆开，再拼回接近块大小的块；仍超长则硬切。',
            process_steps=[
                '用你选的分隔符（如空行）把全文拆成碎片；匹配到的分隔符本身会被丢掉。',
                '把相邻碎片尽量拼回去，拼到接近且不超过「块大小」。',
                '若某一块中间再也找不到分隔符、却仍超过块大小：再按字符硬切，相邻硬切子块重叠「重叠长度」字符。',
            ],
            applicable_scenes=['日志', 'FAQ', '固定分隔符的文本'],
            notes=[
                f'分隔符选项来自系统字典 {DocumentSplitSeparatorDict.DICT_TYPE}，仅支持单个字面量',
                '复杂模式请用 REGEX',
            ],
            param_notes=[
                '分隔符：从下拉选一个字面量（如空行 \\n\\n）',
                '块大小：合并目标；只有单块仍超长时才硬切；上限对齐精排单文档字符上限',
                '重叠长度：只在硬切时生效',
            ],
            param_schema={
                'type': 'object',
                'required': ['splitType', 'chunkSize', 'separator'],
                'properties': {
                    'splitType': {'const': 'SEPARATOR'},
                    'chunkSize': {'type': 'integer', 'minimum': 1},
                    'separator': {
                        'type': 'string',
                        'minLength': 1,
                        'dictType': DocumentSplitSeparatorDict.DICT_TYPE,
                    },
                    'overlap': {'type': 'integer', 'minimum': 0},
                },
            },
        ),
        EmbeddingStrategyVo(
            code=SplitType.REGEX.value,
            name=SplitType.REGEX.label,
            summary='先按自定义正则拆开，再拼回接近块大小的块；仍超长则硬切。',
            process_steps=[
                '用你填写的正则把全文拆成碎片（匹配到的分隔内容默认丢掉；题号等「前瞻」模板会把标记留在下一块开头）。',
                '把相邻碎片尽量拼回去，拼到接近且不超过「块大小」。',
                '若某一块仍超过块大小：再按字符硬切，相邻硬切子块重叠「重叠长度」字符。',
            ],
            applicable_scenes=['结构化片段', '特殊格式文本', '题库/FAQ/日志等模式型边界'],
            notes=[
                'regex 须可编译',
                '流程与「分隔符切分」相同，只是切分规则换成正则',
                f'常用模板来自系统字典 {DocumentSplitRegexTemplateDict.DICT_TYPE}，可选后仍可手改',
            ],
            param_notes=[
                '正则表达式：可从常用模板下拉选择，或直接输入/修改',
                '块大小：合并目标；只有单块仍超长时才硬切；上限对齐精排单文档字符上限',
                '重叠长度：只在硬切时生效',
            ],
            param_schema={
                'type': 'object',
                'required': ['splitType', 'chunkSize', 'regex'],
                'properties': {
                    'splitType': {'const': 'REGEX'},
                    'chunkSize': {'type': 'integer', 'minimum': 1},
                    'regex': {
                        'type': 'string',
                        'minLength': 1,
                        'dictType': DocumentSplitRegexTemplateDict.DICT_TYPE,
                    },
                    'overlap': {'type': 'integer', 'minimum': 0},
                },
            },
        ),
        EmbeddingStrategyVo(
            code=SplitType.SMART.value,
            name=SplitType.SMART.label,
            summary='识别全部 Markdown 标题，并把文章按「行」切开；单行太长时再二次切成子块。',
            process_steps=[
                '从上到下按行读文章；识别全部 6 级标题（# ~ ######），维护当前标题路径（一级/二级/…）。',
                '代码块（``` / ~~~）里的 # 不当标题。',
                '切分单位是「行」：标题行一块、正文每一行一块；每块都带上它所在的标题路径。'
                '不会把同一标题下的多行合并成一大段（这与「标题层级切分」不同）。',
                '若某一行长度 ≤ 块大小：该行直接作为一块写入向量库。',
                '若某一行长度 > 块大小：先保留整行作为父片（不入向量库），再按块大小滑动切出多个子片；'
                '相邻子片重叠固定为块大小的 10%（页面不可改），只把子片写入向量库。',
            ],
            applicable_scenes=['复杂 Markdown', '多层级标题文档', '希望保留细粒度行级片段的文档'],
            notes=[
                '固定识别全部 6 级标题，忽略用户 titleLevel',
                '重叠长度由服务端强制为块大小的 10%，页面不可配置',
            ],
            param_notes=[
                '块大小：单行超过该长度才做父子二次切分；子块最长不超过该值；上限对齐精排单文档字符上限',
                '重叠长度：服务端强制为块大小 × 10%，仅在超长行硬切出的子块之间生效',
            ],
            param_schema={
                'type': 'object',
                'required': ['splitType', 'chunkSize'],
                'properties': {
                    'splitType': {'const': 'SMART'},
                    'chunkSize': {'type': 'integer', 'minimum': 1},
                },
            },
        ),
    ]

    @classmethod
    async def list_strategies(cls) -> list[EmbeddingStrategyVo]:
        """返回策略元数据，并把 chunkSize.maximum 写成当前精排单文档字符上限。"""
        max_chars = await RagConfigService.get_rerank_max_doc_chars()
        out: list[EmbeddingStrategyVo] = []
        for item in cls._STRATEGIES:
            schema = deepcopy(item.param_schema)
            props = schema.get('properties') or {}
            chunk = props.get('chunkSize')
            if isinstance(chunk, dict):
                chunk['maximum'] = max_chars
            out.append(item.model_copy(update={'param_schema': schema}))
        return out
