import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.local_embedding_runtime import LocalEmbeddingRuntime  # noqa: E402


def test_ensure_ready_returns_existing_healthy_runtime():
    class Runtime(LocalEmbeddingRuntime):
        def __init__(self):
            super().__init__(auto_start=True)
            self.started = False

        async def health(self):
            return {"status": "healthy", "model": "bge-m3"}

        def _start_process(self):
            self.started = True

    runtime = Runtime()

    payload = asyncio.run(runtime.ensure_ready())

    assert payload["status"] == "healthy"
    assert runtime.started is False


def test_ensure_ready_starts_local_server_and_waits_until_healthy():
    class Runtime(LocalEmbeddingRuntime):
        def __init__(self):
            super().__init__(auto_start=True, startup_timeout_seconds=2)
            self.started = False
            self.health_calls = 0

        async def health(self):
            self.health_calls += 1
            if self.health_calls == 1:
                return {"status": "unhealthy", "detail": "connection refused"}
            return {"status": "healthy", "model": "bge-m3"}

        def _start_process(self):
            self.started = True

    runtime = Runtime()

    payload = asyncio.run(runtime.ensure_ready())

    assert payload["status"] == "healthy"
    assert runtime.started is True
    assert runtime.health_calls == 2


def test_ensure_ready_fails_fast_when_auto_start_disabled():
    class Runtime(LocalEmbeddingRuntime):
        async def health(self):
            return {"status": "unhealthy", "detail": "connection refused"}

    runtime = Runtime(auto_start=False)

    try:
        asyncio.run(runtime.ensure_ready())
    except RuntimeError as exc:
        assert "connection refused" in str(exc)
    else:
        raise AssertionError("ensure_ready should fail when local embedding is unavailable")
