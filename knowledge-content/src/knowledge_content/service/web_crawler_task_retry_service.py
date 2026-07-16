from knowledge_common.config.env import Crawl4aiConfig
from knowledge_common.utils.log_util import logger

from knowledge_content.enums.crawl_task_error_code_enum import CrawlTaskErrorCode
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


class WebCrawlerTaskRetryService:
    """
    爬取任务重试服务层

    负责失败自动重试与用户人工决策升级。

    重试策略（共用 retry_count，不归零；上限取任务 max_retry_count）：
    - PROCESS_DIED：不计重试次数，直接 PENDING 续跑
    - retry_count < max_retry_count：规则自动重试
    - retry_count >= max_retry_count：升级为用户人工决策
    """

    @classmethod
    async def try_auto_retry(cls, task_id: int) -> bool:
        """
        尝试自动重试任务

        分层策略：
        1. PROCESS_DIED：不计次直接续跑
        2. retry_count >= max_retry_count：升级为用户人工决策
        3. 规则重试（递增 retry_count 并发送消息）

        :param task_id: 任务ID
        :return: 是否成功重试
        """
        task = await WebCrawlerTaskService.get_task(task_id)

        # 进程中断：不计重试次数，直接改状态续跑
        if task.error_code == CrawlTaskErrorCode.PROCESS_DIED.value:
            logger.info(f'[Retry] 进程中断续跑（不计次）: task_id={task_id}')
            await WebCrawlerTaskService.requeue_after_process_died(task_id)
            return True

        default_limit = Crawl4aiConfig.crawl4ai_rule_retry_limit
        rule_retry_limit = (
            task.max_retry_count if task.max_retry_count is not None else default_limit
        )
        if task.retry_count >= rule_retry_limit:
            logger.info(
                f'[Retry] 已达规则重试上限: task_id={task_id}, '
                f'retry_count={task.retry_count}/{rule_retry_limit}'
            )
            await cls._handle_final_failure(task_id)
            return False

        logger.info(
            f'[Retry] 规则重试: task_id={task_id}, '
            f'retry_count={task.retry_count}/{rule_retry_limit}'
        )
        return await cls._rule_retry(task_id)

    @classmethod
    async def _rule_retry(cls, task_id: int) -> bool:
        """
        规则重试：重置状态并发送消息触发重新执行

        :param task_id: 任务ID
        :return: 是否重试成功
        """
        await WebCrawlerTaskService.retry_task(task_id)
        return True

    @classmethod
    async def _handle_final_failure(cls, task_id: int) -> None:
        """
        处理最终失败：升级为用户人工决策

        用户可在任务详情页跳转聊天框，通过 Agent（带工具）分析失败原因并调整策略配置后重试。
        人工介入不限制次数；LLM 重试时会抬高 max_retry_count（+= crawl4ai_rule_retry_limit）。

        :param task_id: 任务ID
        """
        await WebCrawlerTaskService.update_task_status(task_id, CrawlTaskStatus.USER_DECISION.value)
        logger.info(f'[Retry] 升级为用户决策: task_id={task_id}')
