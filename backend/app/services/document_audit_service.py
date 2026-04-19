from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.infra.lightrag_client import LightRAGClient
from app.infra.repositories.document_repository import DocumentRepository
from app.services.local_embedding_runtime import LocalEmbeddingRuntime
from config import BASE_DIR, DATA_DIR, DOC_DIR


class DocumentAuditService:
    def __init__(
        self,
        *,
        document_repository: Optional[DocumentRepository] = None,
        data_dir: Path = DATA_DIR,
        doc_dir: Path = DOC_DIR,
        classified_dir: Optional[Path] = None,
        lightrag_client=None,
        local_embedding_runtime=None,
    ):
        self.data_dir = Path(data_dir)
        self.doc_dir = Path(doc_dir)
        self.classified_dir = Path(classified_dir or (BASE_DIR / "classified_docs"))
        self.document_repository = document_repository or DocumentRepository(data_dir=self.data_dir)
        self.lightrag_client = lightrag_client or LightRAGClient()
        self.local_embedding_runtime = local_embedding_runtime or LocalEmbeddingRuntime()

    async def audit(self) -> Dict:
        documents = list(self.document_repository.list_all() or [])
        document_paths = {
            str(Path(item.get("filepath")).resolve())
            for item in documents
            if isinstance(item, dict) and item.get("filepath")
        }
        local_files = self._list_local_files()
        legacy_json_documents = self._list_legacy_json_documents()
        missing_file_documents = [
            item.get("id")
            for item in documents
            if isinstance(item, dict) and not self._path_exists(item.get("filepath", ""))
        ]
        pending_ingest_documents = [
            item.get("id")
            for item in documents
            if isinstance(item, dict) and (item.get("ingest_status") or "").lower() in {"queued", "processing"}
        ]
        untracked_local_files = sorted(path for path in local_files if path not in document_paths)

        try:
            lightrag = await self.lightrag_client.health()
        except Exception as exc:
            lightrag = {"status": "unhealthy", "detail": str(exc)}

        try:
            local_embedding = await self.local_embedding_runtime.health()
        except Exception as exc:
            local_embedding = {"status": "unhealthy", "detail": str(exc)}

        return {
            "sqlite_documents": len(documents),
            "local_files": len(local_files),
            "legacy_json_documents": len(legacy_json_documents),
            "pending_ingest_documents": len(pending_ingest_documents),
            "missing_file_documents": len(missing_file_documents),
            "untracked_local_files": untracked_local_files,
            "lightrag": lightrag,
            "local_embedding": local_embedding,
        }

    def register_local_only_documents(self) -> int:
        documents = list(self.document_repository.list_all() or [])
        tracked_paths = {
            str(Path(item.get("filepath")).resolve())
            for item in documents
            if isinstance(item, dict) and item.get("filepath")
        }
        self._remove_duplicate_local_only_documents(documents)

        created = 0
        for file_path in self._iter_business_files():
            resolved = str(file_path.resolve())
            if resolved in tracked_paths:
                continue

            mtime = file_path.stat().st_mtime
            payload = {
                "id": str(uuid.uuid4()),
                "filename": file_path.name,
                "filepath": resolved,
                "file_type": file_path.suffix.lower(),
                "created_at": mtime,
                "created_at_iso": datetime.fromtimestamp(mtime).isoformat(),
                "updated_at": datetime.now().isoformat(),
                "preview_content": "",
                "full_content_length": 0,
                "parser_name": None,
                "extraction_status": "pending",
                "ingest_status": "local_only",
                "ingest_error": None,
                "lightrag_track_id": None,
                "lightrag_doc_id": None,
                "last_status_sync_at": None,
            }
            if self.document_repository.upsert(payload):
                tracked_paths.add(resolved)
                created += 1
        return created

    def _remove_duplicate_local_only_documents(self, documents: List[Dict]) -> None:
        for item in documents:
            if not isinstance(item, dict):
                continue
            if str(item.get("ingest_status") or "").lower() != "local_only":
                continue
            document_id = str(item.get("id") or "").strip()
            filepath = str(item.get("filepath") or "").strip()
            if not document_id or not filepath:
                continue
            try:
                resolved = str(Path(filepath).resolve())
            except Exception:
                continue
            if self._is_lightrag_shadow_file(Path(resolved)):
                self.document_repository.delete(document_id)

    def _list_local_files(self) -> List[str]:
        results: List[str] = []
        for path in self._iter_business_files():
            results.append(str(path.resolve()))
        return sorted(results)

    def _iter_business_files(self):
        for root in [self.doc_dir, self.classified_dir]:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if self._should_ignore_local_file(path):
                    continue
                yield path

    def _list_legacy_json_documents(self) -> List[Dict]:
        payloads: List[Dict] = []
        if not self.data_dir.exists():
            return payloads
        for path in self.data_dir.glob("*.json"):
            if path.name == "classification_tree.json":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and (data.get("id") or data.get("filename")):
                payloads.append(data)
        return payloads

    @staticmethod
    def _path_exists(value: str) -> bool:
        if not value:
            return False
        try:
            return Path(value).exists()
        except Exception:
            return False

    def _should_ignore_local_file(self, path: Path) -> bool:
        normalized = str(path.resolve())
        if f"{self.doc_dir.resolve()}/test/" in normalized:
            return True
        if self._is_lightrag_shadow_file(path):
            return True
        return False

    @staticmethod
    def _is_lightrag_shadow_file(path: Path) -> bool:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        return "__enqueued__" in resolved.parts
