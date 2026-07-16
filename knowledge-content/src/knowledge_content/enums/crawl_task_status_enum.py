from enum import Enum


class CrawlTaskStatus(str, Enum):
    """crawl_task 爬取任务状态枚举"""

    # 执行中
    PENDING = ('PENDING', '等待执行')                  # 待执行（含重试决策后重新入队）
    RUNNING = ('RUNNING', '执行中')                      # 正在执行
    PAUSED = ('PAUSED', '已暂停')                        # 已暂停

    # 中间状态
    COMPLETED = ('COMPLETED', '已完成')                  # 爬取完成（待文档落库）
    CONVERTING = ('CONVERTING', '落库中')                # 文档落库中（枚举值不变）
    CONVERT_FAILED = ('CONVERT_FAILED', '转换失败')       # 文档落库失败，等待重试

    # 终态
    CONVERTED = ('CONVERTED', '已转换')                  # 已写入知识库文档
    FAILED = ('FAILED', '执行失败')                      # 最终失败
    USER_DECISION = ('USER_DECISION', '待决策')           # 待用户决策

    def __new__(cls, value: str, label: str) -> 'CrawlTaskStatus':
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        return obj
