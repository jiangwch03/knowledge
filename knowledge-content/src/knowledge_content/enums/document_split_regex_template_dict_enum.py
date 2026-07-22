"""文档切分正则模板字典配置"""


class DocumentSplitRegexTemplateDict:
    """sys_dict_type.dict_type 固定值；选项在 sys_dict_data 维护。

    dict_value 为可直接交给 re.compile 的正则；前端可选模板后仍允许手改。
    """

    DICT_TYPE = 'document_split_regex_template'
