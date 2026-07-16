from enum import Enum


class CrawlTaskErrorCode(str, Enum):
    """crawl_task 爬取任务级错误码枚举

    用于任务表（knowledge_web_crawler_task），记录任务整体的执行结果，
    面向用户展示，不用于精准重试决策。

    与 CrawlUrlErrorCode 的区别：
    - CrawlTaskErrorCode：任务级聚合错误码，用于任务表，面向用户展示
    - CrawlUrlErrorCode：URL 级细分错误码，用于 URL 记录表，面向重试决策
    """

    # 爬取结果类（任务级聚合）
    ALL_CRAWL_FAILED = ('ALL_CRAWL_FAILED', '全部URL爬取失败', 'danger')          # 全部URL爬取失败
    PARTIAL_CRAWL_FAILED = ('PARTIAL_CRAWL_FAILED', '部分URL爬取失败', 'warning')  # 部分URL爬取失败

    # 异常类
    BIZ_ERROR = ('BIZ_ERROR', '业务异常', 'danger')                  # 业务异常（如重复爬取检查失败）
    EXEC_ERROR = ('EXEC_ERROR', '执行异常', 'danger')                # 执行异常（未预期异常）
    CONSUMER_ERROR = ('CONSUMER_ERROR', '消费者执行异常', 'danger')   # 消费者执行异常
    DOC_PERSIST_ERROR = ('DOC_PERSIST_ERROR', '文档持久化失败', 'danger')  # 文档持久化失败
    TIMEOUT = ('TIMEOUT', '任务超时', 'warning')                     # 任务执行超时（活执行器收到取消标志后自报）
    PROCESS_DIED = ('PROCESS_DIED', '进程中断', 'warning')           # 执行进程已死（锁已释放），僵尸 RUNNING 收尸

    def __new__(cls, value: str, label: str, type_: str) -> 'CrawlTaskErrorCode':
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        obj.type = type_
        return obj
