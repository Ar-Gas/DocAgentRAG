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
from app.services.lightrag_dev_config import build_lightrag_env, render_lightrag_env
from config import (
    BASE_DIR,
    DOUBAO_API_KEY,
    DOUBAO_DEFAULT_LLM_MODEL,
    DOUBAO_LLM_API_URL,
    LIGHTRAG_AUTO_START,
    LIGHTRAG_BASE_URL,
    LIGHTRAG_ENV_PATH,
    LIGHTRAG_HEALTH_TIMEOUT_SECONDS,
    LIGHTRAG_STARTUP_TIMEOUT_SECONDS,
    LOCAL_EMBEDDING_DIM,
    LOCAL_EMBEDDING_MODEL_NAME,
)


class LightRAGRuntime:
    def __init__(
        self,
        *,
        base_url: str = LIGHTRAG_BASE_URL,
        auto_start: bool = LIGHTRAG_AUTO_START,
        health_timeout_seconds: float = LIGHTRAG_HEALTH_TIMEOUT_SECONDS,
        startup_timeout_seconds: float = LIGHTRAG_STARTUP_TIMEOUT_SECONDS,
        backend_dir: Path = BASE_DIR,
        env_path: str | Path = LIGHTRAG_ENV_PATH,
        python_executable: Optional[str] = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.auto_start = auto_start
        self.health_timeout_seconds = float(health_timeout_seconds)
        self.startup_timeout_seconds = float(startup_timeout_seconds)
        self.backend_dir = Path(backend_dir)
        self.env_path = Path(env_path)
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
                "liveness": "down",
                "readiness": "unready",
                "base_url": self.base_url,
                "detail": f"LightRAG server unavailable: {exc}",
            }

        if response.status_code < 200 or response.status_code >= 300:
            return {
                "status": "unhealthy",
                "liveness": "down",
                "readiness": "unready",
                "base_url": self.base_url,
                "detail": f"LightRAG returned {response.status_code}: {response.text}",
            }

        try:
            payload = response.json()
        except Exception as exc:
            return {
                "status": "unhealthy",
                "liveness": "up",
                "readiness": "unready",
                "base_url": self.base_url,
                "detail": f"LightRAG returned invalid JSON: {exc}",
            }

        if not isinstance(payload, dict):
            payload = {"data": payload}
        upstream_status = str(payload.get("status") or "unknown").lower()
        normalized = {
            **payload,
            "status": "healthy" if upstream_status == "healthy" else "degraded",
            "liveness": "up",
            "readiness": "ready" if upstream_status == "healthy" else "unready",
            "base_url": self.base_url,
        }
        return normalized

    async def ensure_ready(self) -> Dict[str, Any]:
        async with self._lock:
            current = await self.health()
            if current.get("status") == "healthy":
                return current

            if not self.auto_start:
                raise RuntimeError(current.get("detail") or "LightRAG server unavailable")

            self._write_env_file()
            self._start_process()
            deadline = time.monotonic() + max(self.startup_timeout_seconds, 0.1)
            last_payload = current
            while time.monotonic() < deadline:
                await asyncio.sleep(0.5)
                last_payload = await self.health()
                if last_payload.get("status") == "healthy":
                    return last_payload
                if self._process is not None and self._process.poll() is not None:
                    break

            detail = last_payload.get("detail") or "LightRAG server unavailable"
            if self._process is not None and self._process.poll() is not None:
                detail = f"{detail}; process exited with code {self._process.returncode}"
            raise RuntimeError(detail)

    def _write_env_file(self) -> None:
        env_values = build_lightrag_env(
            root_dir=self.backend_dir.parent,
            doubao_api_key=DOUBAO_API_KEY,
            doubao_llm_api_url=DOUBAO_LLM_API_URL,
            doubao_llm_model=DOUBAO_DEFAULT_LLM_MODEL,
            embedding_host="http://127.0.0.1:8011/v1",
            embedding_model=LOCAL_EMBEDDING_MODEL_NAME,
            embedding_dim=LOCAL_EMBEDDING_DIM,
        )
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text(render_lightrag_env(env_values), encoding="utf-8")

    def _load_env_file(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self.env_path.exists():
            return values
        for raw_line in self.env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _start_process(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return

        script_path = self.backend_dir / "scripts" / "run_lightrag_server.py"
        log_dir = self.backend_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "lightrag_server.log"
        env = dict(os.environ)
        env.update(self._load_env_file())
        env["PYTHONUNBUFFERED"] = "1"

        try:
            with log_path.open("a", encoding="utf-8") as log_handle:
                self._process = subprocess.Popen(
                    [self.python_executable, str(script_path)],
                    cwd=str(self.backend_dir),
                    env=env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            logger.info(
                "lightrag_server_starting pid={} base_url={} log={}",
                self._process.pid if self._process else None,
                self.base_url,
                log_path,
            )
        except Exception as exc:
            raise RuntimeError(f"LightRAG server unavailable: {exc}") from exc
