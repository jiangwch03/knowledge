from abc import ABC, abstractmethod

from knowledge_content.splitter.vo import TextSegmentVo


class BaseDocumentSplitter(ABC):
    """文档切分器基类，定义通用接口。"""

    @abstractmethod
    def split(self, text: str) -> list[TextSegmentVo]:
        raise NotImplementedError
