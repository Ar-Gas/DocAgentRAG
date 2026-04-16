from pathlib import Path
from typing import Dict, List, Optional

from app.infra.metadata_store import get_metadata_store


class DocumentSegmentRepository:
    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self._store = get_metadata_store(data_dir=data_dir, db_path=db_path)

    def replace(self, document_id: str, segments: List[Dict]) -> bool:
        return self._store.replace_document_segments(document_id, segments)

    def list(self, document_id: str) -> List[Dict]:
        return self._store.list_document_segments(document_id)
