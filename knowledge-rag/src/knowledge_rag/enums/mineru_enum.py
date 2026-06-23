
from enum import Enum


class MinerUParseModeEnum(str, Enum):
    """MineU 解析模式扩展点

    数据库层使用 document/html，MinerU API 层使用 normal/html。
    通过 from_document_mode() 方法完成映射转换。
    """

    NORMAL = 'normal'
    HTML = 'html'

    @classmethod
    def from_document_mode(cls, mode: str) -> 'MinerUParseModeEnum':
        """将数据库层的解析模式映射为 MinerU API 枚举值

        Args:
            mode: 数据库存储值，'document' 或 'html'

        Returns:
            对应的 MinerUParseModeEnum 枚举成员
        """
        _MAPPING = {
            'document': cls.NORMAL,
            'html': cls.HTML,
        }
        enum_val = _MAPPING.get(mode)
        if enum_val is None:
            raise ValueError(f'不支持的数据库解析模式: {mode!r}，仅支持 document、html')
        return enum_val


class FormulaSwitch(str, Enum):
    """公式识别开关枚举（0-否 1-是）"""

    NO = '0'
    YES = '1'


class TableSwitch(str, Enum):
    """表格识别开关枚举（0-否 1-是）"""

    NO = '0'
    YES = '1'


class OcrSwitch(str, Enum):
    """
    OCR 开关枚举

    NO: 关闭 (0)
    YES: 开启 (1)
    """

    NO = '0'
    YES = '1'

