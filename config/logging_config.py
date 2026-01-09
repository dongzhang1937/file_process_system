# log_config.py
import logging
import sys
from loguru import logger

# 1. 定义拦截器：将标准 logging 的日志转发到 loguru
class InterceptHandler(logging.Handler):
    def emit(self, record):
        # 获取对应的 Loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 找到调用日志的原始栈帧
        frame, depth = logging.currentframe(), 2
        if frame is None:
            # 如果无法获取栈帧，直接使用当前信息
            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )
            return
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        # 将日志发送给 Loguru
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

# 2. 初始化日志配置的函数
def setup_logging():
    # 移除 Loguru 默认的处理器 (通常是 stderr)
    logger.remove()

    # --- 配置输出目标 (Sink) ---
    
    # A. 输出到控制台 (Console)
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # B. 输出到文件 (File) - 每天轮转，保留 10 天
    logger.add(
        "./file_process/logs/app_{time:YYYY-MM-DD}.log",  # 日志文件路径
        rotation="00:00",                   # 每天 0 点创建新文件
        retention="10 days",                # 保留最近 10 天的日志
        level="DEBUG",                      # 文件记录更详细的 DEBUG 级别
        encoding="utf-8",
        enqueue=True                        # 异步写入，线程安全
    )

    # --- 接管标准日志 ---
    
    # 获取 Python 标准 logging 的 root logger
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # 特别处理：让 Flask 和 Werkzeug (HTTP服务器) 的日志也走 Loguru
    for logger_name in ("werkzeug", "flask.app", "gunicorn", "gunicorn.access", "gunicorn.error"):
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()] # 替换原有 handler
        logging_logger.propagate = False # 防止重复打印

# 导出 logger 对象供其他模块直接使用
__all__ = ["logger", "setup_logging"]