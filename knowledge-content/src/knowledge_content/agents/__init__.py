"""
网页爬取 Agent 模块

采用 ReAct + Human-in-the-Loop 组合架构：
- ReAct 循环（最多3轮）：调用分析工具链，动态决策
- Human-in-the-Loop：策略确认点等待用户审批
"""
