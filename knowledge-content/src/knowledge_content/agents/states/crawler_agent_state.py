"""
网页爬取 Agent 状态定义 - 父图业务字段

公共业务字段由 Supervisor / Planning 共享：task 委派时会拷贝除 messages 外的同名 key。
query_crawl_task / Planning 终稿经 middleware 写入，避免子 agent 冷启动断档。
对话 messages 由 SupervisorState 持有。
"""

from typing import NotRequired, TypedDict


class CrawlerAgentState(TypedDict):
    """爬虫 Agent 公共字段——父图和子图共享的业务上下文"""

    # 当前会话目标入口 URL（查任务 / 开爬 / 调规划时写入）
    target_url: NotRequired[str]
    # 当前关联任务 ID（修失败 / 改范围等）
    task_id: NotRequired[int]
    # 最新版 crawl4ai 策略配置（查任务详情或规划终稿回流）
    crawl_config: NotRequired[dict]
    # 失败修复：失败 URL 列表
    failed_urls: NotRequired[list[str]]
    # 失败修复：失败原因摘要
    failed_reason: NotRequired[str]
