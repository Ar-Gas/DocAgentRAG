from __future__ import annotations

import logging
import json
import sys
import time
import uuid
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any, Optional

from loguru import logger as _base_logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOG_FILE = BACKEND_DIR / "logs" / "app.log"
DEFAULT_LOG_LEVEL = "INFO"

request_id_context_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

_CONFIGURED_SIGNATURE: tuple[str, str] | None = None


def get_request_id() -> str:
    return request_id_context_var.get() or "-"


def get_request_id_from_request(request: Request | None) -> str:
    if request is not None:
        state = getattr(request, "state", None)
        request_id = getattr(state, "request_id", None) if state is not None else None
        if request_id:
            return str(request_id)
    return get_request_id()


def _patch_record(record: dict) -> None:
    extra = record["extra"]
    extra["request_id"] = extra.get("request_id") or get_request_id()


logger = _base_logger.patch(_patch_record)


CONSOLE_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level:<8}</level> | "
    "<cyan>rid={extra[request_id]}</cyan> | "
    "<cyan>{name}:{function}:{line}</cyan> - "
    "<level>{message}</level>\n{exception}"
)

FILE_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level:<8} | "
    "rid={extra[request_id]} | "
    "{name}:{function}:{line} - "
    "{message}\n{exception}"
)


def _normalize_log_level(level: str | int) -> tuple[str | int, int]:
    if isinstance(level, int):
        return level, level

    name = str(level).upper()
    level_no = logging.getLevelName(name)
    if isinstance(level_no, int):
        return name, level_no
    return DEFAULT_LOG_LEVEL, logging.INFO


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.bind(logger_name=record.name).opt(
            depth=depth,
            exception=record.exc_info,
        ).log(level, record.getMessage())


def setup_logging(
    level: str | int = DEFAULT_LOG_LEVEL,
    log_file: str | Path | None = None,
    force: bool = False,
) -> None:
    global _CONFIGURED_SIGNATURE

    target_log_file = Path(log_file) if log_file is not None else DEFAULT_LOG_FILE
    target_log_file.parent.mkdir(parents=True, exist_ok=True)

    normalized_level, level_no = _normalize_log_level(level)
    signature = (str(target_log_file), str(normalized_level))
    if _CONFIGURED_SIGNATURE == signature and not force:
        return

    logger.remove()
    logger.add(
        sys.stderr,
        level=normalized_level,
        colorize=True,
        format=CONSOLE_LOG_FORMAT,
        backtrace=False,
        diagnose=False,
    )
    logger.add(
        str(target_log_file),
        level=normalized_level,
        colorize=False,
        format=FILE_LOG_FORMAT,
        rotation="00:00",
        retention="10 days",
        encoding="utf-8",
        backtrace=True,
        diagnose=False,
    )

    intercept_handler = InterceptHandler()

    logging.root.handlers = [intercept_handler]
    logging.root.setLevel(level_no)
    logging.captureWarnings(True)

    managed_logger_names = (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
    )
    for logger_name in managed_logger_names:
        target_logger = logging.getLogger(logger_name)
        target_logger.handlers = [intercept_handler]
        target_logger.propagate = False
        target_logger.setLevel(level_no)

    for logger_name, logger_obj in list(logging.root.manager.loggerDict.items()):
        if logger_name in managed_logger_names:
            continue
        if isinstance(logger_obj, logging.Logger) and logger_obj.handlers:
            logger_obj.handlers = []
            logger_obj.propagate = True

    _CONFIGURED_SIGNATURE = signature


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_context_var.set(request_id)
        request.state.request_id = request_id

        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "-"
        bound_logger = logger.bind(request_id=request_id)

        bound_logger.info(
            "request_started method={} path={} client_ip={}",
            request.method,
            request.url.path,
            client_ip,
        )

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            bound_logger.error(
                "request_failed method={} path={} client_ip={} duration_ms={:.2f}",
                request.method,
                request.url.path,
                client_ip,
                duration_ms,
            )
            raise
        else:
            duration_ms = (time.perf_counter() - start_time) * 1000
            response.headers["X-Request-ID"] = request_id
            bound_logger.info(
                "request_completed method={} path={} status_code={} duration_ms={:.2f}",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response
        finally:
            request_id_context_var.reset(token)


def get_logger(name: str):
    return logger.bind(component=name)


def log_retrieval(func):
    wrapped_logger = get_logger(func.__module__ or __name__)

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        if isinstance(result, list):
            count: Any = len(result)
        elif isinstance(result, dict):
            count = len(result.get("results", result.get("items", [])))
        else:
            count = "N/A"

        query = args[0] if args and isinstance(args[0], str) else kwargs.get("query", "")
        wrapped_logger.info(
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


__all__ = [
    "logger",
    "setup_logging",
    "InterceptHandler",
    "RequestContextMiddleware",
    "request_id_context_var",
    "get_request_id",
    "get_request_id_from_request",
    "get_logger",
    "log_retrieval",
]
