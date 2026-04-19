from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import httpx

from app.services.errors import AppServiceError
from config import LIGHTRAG_API_KEY, LIGHTRAG_BASE_URL, LIGHTRAG_TIMEOUT_SECONDS


class LightRAGClient:
    def __init__(
        self,
        base_url: str = LIGHTRAG_BASE_URL,
        api_key: str = LIGHTRAG_API_KEY,
        timeout_seconds: float = LIGHTRAG_TIMEOUT_SECONDS,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            return {}
        return {"X-API-Key": self.api_key}

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(method, url, headers=self._headers(), **kwargs)
        except Exception as exc:
            raise AppServiceError(4001, f"LightRAG request failed: {exc}") from exc

        if response.status_code < 200 or response.status_code >= 300:
            detail = self._response_detail(response)
            raise AppServiceError(4001, f"LightRAG returned {response.status_code}: {detail}")

        try:
            payload = response.json()
        except Exception as exc:
            raise AppServiceError(4002, f"LightRAG returned invalid JSON: {exc}") from exc

        return payload if isinstance(payload, dict) else {"data": payload}

    @staticmethod
    def _response_detail(response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return str(payload.get("detail") or payload.get("message") or payload)
        except Exception:
            pass
        return getattr(response, "text", "") or "empty response"

    async def health(self) -> Dict[str, Any]:
        return await self._request("GET", "/health")

    async def upload_file(self, file_path: str, filename: str) -> Dict[str, Any]:
        path = Path(file_path)
        with path.open("rb") as handle:
            files = {"file": (filename or path.name, handle)}
            return await self._request("POST", "/documents/upload", files=files)

    async def get_track_status(self, track_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/documents/track_status/{track_id}")

    async def reprocess_failed_documents(self) -> Dict[str, Any]:
        return await self._request("POST", "/documents/reprocess_failed")

    async def list_documents_paginated(self, page: int = 1, page_size: int = 100) -> Dict[str, Any]:
        return await self._request(
            "POST",
            "/documents/paginated",
            json={"page": page, "page_size": page_size},
        )

    async def query_data(self, query: str, mode: str = "hybrid", top_k: int = 10) -> Dict[str, Any]:
        return await self._request(
            "POST",
            "/query/data",
            json={"query": query, "mode": mode, "top_k": top_k},
        )

    async def query(
        self,
        query: str,
        mode: str = "hybrid",
        *,
        include_references: bool = True,
        include_chunk_content: bool = True,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "query": query,
            "mode": mode,
            "include_references": include_references,
            "include_chunk_content": include_chunk_content,
        }
        if conversation_history:
            payload["conversation_history"] = conversation_history
        return await self._request("POST", "/query", json=payload)

    async def list_graph_labels(self) -> Dict[str, Any]:
        return await self._request("GET", "/graph/label/list")

    async def get_graph(self, label: str, max_depth: int = 3, max_nodes: int = 1000) -> Dict[str, Any]:
        return await self._request(
            "GET",
            "/graphs",
            params={"label": label, "max_depth": max_depth, "max_nodes": max_nodes},
        )
