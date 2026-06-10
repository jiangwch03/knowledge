from datetime import datetime

from knowledge_common.config.env import AppConfig


def job(*args, **kwargs) -> None:
    """
    定时任务执行同步函数示例
    """
    print(args)
    print(kwargs)
    print(f'{datetime.now()} {AppConfig.app_name} 同步函数执行了')


async def async_job(*args, **kwargs) -> None:
    """
    定时任务执行异步函数示例
    """
    print(args)
    print(kwargs)
    print(f'{datetime.now()} {AppConfig.app_name} 异步函数执行了')
