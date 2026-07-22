"""文档切分分隔符字典配置"""


class DocumentSplitSeparatorDict:
    """sys_dict_type.dict_type 固定值；选项在 sys_dict_data 维护。

    dict_value 存可见转义串（如 \\n\\n、\\t、\\u0020），切分前再解码成真实字符，
    避免换行/空格在字典管理页显示成空白。
    """

    DICT_TYPE = 'document_split_separator'

    @staticmethod
    def decode(value: str) -> str:
        """将字典键值中的可见转义解码为实际分隔符。

        已是真实控制字符的旧数据保持不变；普通标点原样返回。
        """
        if not value:
            return value
        return (
            value.replace('\\n', '\n')
            .replace('\\t', '\t')
            .replace('\\r', '\r')
            .replace('\\u0020', ' ')
        )
