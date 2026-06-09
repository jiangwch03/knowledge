from datetime import datetime


def job(*args, **kwargs) -> None:
    """
    定时任务执行同步函数示例
    """
    print(args)
    print(kwargs)
    print(f'{datetime.now()} {AppConfig.APP_NAME} 同步函数执行了')


async def async_job(*args, **kwargs) -> None:
    """
    定时任务执行异步函数示例
    """
    print(args)
    print(kwargs)
    print(f'{datetime.now()} {AppConfig.APP_NAME} 异步函数执行了')
