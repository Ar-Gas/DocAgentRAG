import asyncio
import logging
import os
import sys
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
import httpx
from starlette.requests import Request

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import generic_exception_handler  # noqa: E402
from app.core.logger import (  # noqa: E402
    InterceptHandler,
    RequestContextMiddleware,
    request_id_context_var,
    setup_logging,
)


def test_setup_logging_intercepts_standard_logging_and_uses_default_request_id(tmp_path: Path):
    log_file = tmp_path / "app.log"
    token = request_id_context_var.set(None)
    try:
        setup_logging(log_file=log_file, force=True)
        logging.getLogger("uvicorn.error").warning("observability smoke")
    finally:
        request_id_context_var.reset(token)

    text = log_file.read_text(encoding="utf-8")
    assert "observability smoke" in text
    assert "rid=-" in text
    assert any(isinstance(handler, InterceptHandler) for handler in logging.getLogger().handlers)


def test_request_context_middleware_sets_response_request_id_and_logs(tmp_path: Path):
    log_file = tmp_path / "requests.log"
    setup_logging(log_file=log_file, force=True)

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async def _run_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/ping")

    response = asyncio.run(_run_request())

    request_id = response.headers["X-Request-ID"]
    UUID(request_id)
    assert response.status_code == 200

    text = log_file.read_text(encoding="utf-8")
    assert "request_started" in text
    assert "request_completed" in text
    assert f"rid={request_id}" in text


def test_generic_exception_handler_logs_stack_and_sets_request_id_header(tmp_path: Path):
    log_file = tmp_path / "errors.log"
    setup_logging(log_file=log_file, force=True)

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/boom",
            "raw_path": b"/boom",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )
    request.state.request_id = "req-test-123"

    response = asyncio.run(generic_exception_handler(request, RuntimeError("boom")))

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-test-123"

    text = log_file.read_text(encoding="utf-8")
    assert "req-test-123" in text
    assert "RuntimeError: boom" in text
