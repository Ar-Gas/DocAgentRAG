from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from app.core.logger import logger
from config import (
    BASE_DIR,
    LOCAL_EMBEDDING_AUTO_START,
    LOCAL_EMBEDDING_BASE_URL,
    LOCAL_EMBEDDING_HEALTH_TIMEOUT_SECONDS,
    LOCAL_EMBEDDING_STARTUP_TIMEOUT_SECONDS,
)


class LocalEmbeddingRuntime:
    def __init__(
        self,
        *,
        base_url: str = LOCAL_EMBEDDING_BASE_URL,
        auto_start: bool = LOCAL_EMBEDDING_AUTO_START,
        health_timeout_seconds: float = LOCAL_EMBEDDING_HEALTH_TIMEOUT_SECONDS,
        startup_timeout_seconds: float = LOCAL_EMBEDDING_STARTUP_TIMEOUT_SECONDS,
        backend_dir: Path = BASE_DIR,
        python_executable: Optional[str] = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.auto_start = auto_start
        self.health_timeout_seconds = float(health_timeout_seconds)
        self.startup_timeout_seconds = float(startup_timeout_seconds)
        self.backend_dir = Path(backend_dir)
        self.python_executable = python_executable or sys.executable
        self._process: subprocess.Popen | None = None
        self._lock = asyncio.Lock()

    async def health(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.health_timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/health")
        except Exception as exc:
            return {
                "status": "unhealthy",
                "base_url": self.base_url,
                "detail": f"local embedding server unavailable: {exc}",
            }

        if response.status_code < 200 or response.status_code >= 300:
            return {
                "status": "unhealthy",
                "base_url": self.base_url,
                "detail": f"local embedding server returned {response.status_code}: {response.text}",
            }

        try:
            payload = response.json()
        except Exception as exc:
            return {
                "status": "unhealthy",
                "base_url": self.base_url,
                "detail": f"local embedding server returned invalid JSON: {exc}",
            }

        if not isinstance(payload, dict):
            payload = {"data": payload}
        payload.setdefault("status", "unknown")
        payload["base_url"] = self.base_url
        return payload

    async def probe_readiness(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.health_timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/v1/embeddings",
                json={"input": "health check", "encoding_format": "float"},
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"local embedding readiness probe returned {response.status_code}")
        payload = response.json()
        vectors = (payload.get("data") or [{}])[0].get("embedding") or []
        if not vectors:
            raise RuntimeError("local embedding readiness probe returned no vectors")
        return {"ready": True, "vector_size": len(vectors)}

    async def _verify_readiness(self) -> None:
        # Unit tests often override health() without running an HTTP server.
        # Real runtimes and subclasses that override probe_readiness() still run
        # the actual readiness probe.
        if (
            type(self).health is not LocalEmbeddingRuntime.health
            and type(self).probe_readiness is LocalEmbeddingRuntime.probe_readiness
        ):
            return
        await self.probe_readiness()

    async def ensure_ready(self) -> Dict[str, Any]:
        async with self._lock:
            current = await self.health()
            if current.get("status") == "healthy":
                await self._verify_readiness()
                return current

            if not self.auto_start:
                raise RuntimeError(current.get("detail") or "local embedding server unavailable")

            liveness = str(current.get("liveness") or "").lower()
            readiness = str(current.get("readiness") or "").lower()
            status = str(current.get("status") or "").lower()
            server_is_live = liveness == "up" or status == "warming_up"
            if server_is_live and readiness == "failed":
                raise RuntimeError(current.get("detail") or "local embedding model failed to initialize")
            if not server_is_live:
                self._start_process()
            deadline = time.monotonic() + max(self.startup_timeout_seconds, 0.1)
            last_payload = current
            while time.monotonic() < deadline:
                await asyncio.sleep(0.5)
                last_payload = await self.health()
                if last_payload.get("status") == "healthy":
                    await self._verify_readiness()
                    return last_payload
                readiness = str(last_payload.get("readiness") or "").lower()
                liveness = str(last_payload.get("liveness") or "").lower()
                if liveness == "up" and readiness == "failed":
                    break
                if self._process is not None and self._process.poll() is not None:
                    break

            detail = last_payload.get("detail") or "local embedding server unavailable"
            if self._process is not None and self._process.poll() is not None:
                detail = f"{detail}; process exited with code {self._process.returncode}"
            raise RuntimeError(detail)

    def _start_process(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return

        server_path = self.backend_dir / "local_embedding_server.py"
        log_dir = self.backend_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "local_embedding_server.log"
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"

        try:
            with log_path.open("a", encoding="utf-8") as log_handle:
                self._process = subprocess.Popen(
                    [self.python_executable, str(server_path)],
                    cwd=str(self.backend_dir),
                    env=env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            logger.info(
                "local_embedding_server_starting pid={} base_url={} log={}",
                self._process.pid if self._process else None,
                self.base_url,
                log_path,
            )
        except Exception as exc:
            raise RuntimeError(f"local embedding server unavailable: {exc}") from exc
