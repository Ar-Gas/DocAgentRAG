import asyncio

from app.services.lightrag_runtime import LightRAGRuntime


def test_lightrag_runtime_health_reports_degraded_when_upstream_is_alive_but_not_ready():
    class Runtime(LightRAGRuntime):
        async def health(self):
            return {
                "status": "degraded",
                "liveness": "up",
                "readiness": "unready",
                "detail": "embedding dependency is not ready",
            }

    payload = asyncio.run(Runtime(auto_start=False).health())

    assert payload["status"] == "degraded"
    assert payload["liveness"] == "up"
    assert payload["readiness"] == "unready"
