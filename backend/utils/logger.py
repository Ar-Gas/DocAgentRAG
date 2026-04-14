"""
统一日志模块。

用法：
    from utils.logger import get_logger, log_retrieval, setup_logging

    logger = get_logger(__name__)

    @log_retrieval
    def my_search_func(query, ...):
        ...
"""
import json
import logging
import time
from functools import wraps
from typing import Any

_ROOT_LOGGER = "docagent"


def setup_logging(level: int = logging.INFO) -> None:
    """配置根 logger，统一格式输出到 stderr。重复调用幂等。"""
    root = logging.getLogger(_ROOT_LOGGER)
    if root.handlers:
        return  # 已配置，跳过

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger（自动挂载到 docagent 根节点）"""
    if not name.startswith(_ROOT_LOGGER):
        name = f"{_ROOT_LOGGER}.{name}"
    return logging.getLogger(name)


def log_retrieval(func):
    """
    检索函数装饰器：自动记录 query / mode / latency_ms / result_count。

    适用于返回 list 或 dict（含 results 键）的检索函数。
    """
    _logger = get_logger(func.__module__ or __name__)

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        # 尝试提取 result_count
        if isinstance(result, list):
            count: Any = len(result)
        elif isinstance(result, dict):
            count = len(result.get("results", result.get("items", [])))
        else:
            count = "N/A"

        # 尝试从第一个位置参数提取 query
        query = args[0] if args and isinstance(args[0], str) else kwargs.get("query", "")

        _logger.info(
            json.dumps(
                {
                    "event": "retrieval",
                    "func": func.__qualname__,
                    "query": (query[:80] + "...") if len(query) > 80 else query,
                    "latency_ms": elapsed_ms,
                    "result_count": count,
                },
                ensure_ascii=False,
            )
        )
        return result

    return wrapper
