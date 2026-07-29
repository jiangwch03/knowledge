"""
通用工厂类

封装 LangChain 大模型实例等跨项目复用的创建逻辑。
"""

from knowledge_common.common.factory.dashscope_model_factory import DashScopeModelFactory
from knowledge_common.common.factory.langchain_model_factory import LangChainModelFactory

__all__ = ['DashScopeModelFactory', 'LangChainModelFactory']
