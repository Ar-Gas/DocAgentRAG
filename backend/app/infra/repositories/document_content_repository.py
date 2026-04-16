from pathlib import Path
from typing import Dict, Optional

from app.infra.metadata_store import get_metadata_store


class DocumentContentRepository:
    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self._store = get_metadata_store(data_dir=data_dir, db_path=db_path)

    def save(
        self,
        document_id: str,
        *,
        full_content: str,
        preview_content: Optional[str] = None,
        extraction_status: str = "ready",
        parser_name: Optional[str] = None,
        extraction_error: Optional[str] = None,
    ) -> bool:
        return self._store.save_document_content(
            document_id,
            full_content=full_content,
            preview_content=preview_content,
            extraction_status=extraction_status,
            parser_name=parser_name,
            extraction_error=extraction_error,
        )

    def get(self, document_id: str) -> Optional[Dict]:
        return self._store.get_document_content(document_id)
