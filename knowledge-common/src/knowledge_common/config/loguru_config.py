from loguru import logger
import sys
import os

# 确保日志目录存在
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging():
    """全局只调用一次，配置所有日志规则"""

    # 移除默认的 console 处理器
    logger.remove()

    # ========== 控制台输出（开发调试）==========
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<<cyan>{function}</cyan>:<<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        level="DEBUG",
        colorize=True,
        enqueue=True,  # 异步，避免阻塞
    )

    # ========== 普通文本日志（按天轮转）==========
    logger.add(
        f"{LOG_DIR}/app_{{time:YYYY-MM-DD}}.log",
        rotation="00:00",  # 每天凌晨轮转
        retention="30 days",  # 保留30天
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO",
        enqueue=True,
        compression="zip",  # 旧日志压缩
    )

    # ========== 错误日志（单独文件，只记录 ERROR 以上）==========
    logger.add(
        f"{LOG_DIR}/error_{{time:YYYY-MM-DD}}.log",
        rotation="1 day",
        retention="60 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
        level="ERROR",
        enqueue=True,
        backtrace=True,  # 记录完整堆栈
        diagnose=True,  # 显示变量值
    )

    # ========== JSON 结构化日志（用于日志收集系统）==========
    logger.add(
        f"{LOG_DIR}/app_{{time:YYYY-MM-DD}}.json",
        rotation="1 day",
        retention="7 days",
        encoding="utf-8",
        serialize=True,  # 输出 JSON
        level="INFO",
        enqueue=True,
        compression="zip",
    )

    logger.info("✅ 日志系统初始化完成")