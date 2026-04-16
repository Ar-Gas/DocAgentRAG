from pathlib import Path
from typing import Dict, List, Optional

from app.infra.metadata_store import get_metadata_store


class DocumentArtifactRepository:
    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self._store = get_metadata_store(data_dir=data_dir, db_path=db_path)

    def save(
        self,
        document_id: str,
        artifact_type: str,
        payload: Dict,
        artifact_id: Optional[str] = None,
    ) -> Optional[str]:
        return self._store.save_document_artifact(document_id, artifact_type, payload, artifact_id)

    def upsert(self, document_id: str, artifact_type: str, payload: Dict) -> Optional[str]:
        return self._store.upsert_document_artifact(document_id, artifact_type, payload)

    def list(self, document_id: str, artifact_type: Optional[str] = None) -> List[Dict]:
        return self._store.list_document_artifacts(document_id, artifact_type)

    def get(self, document_id: str, artifact_type: str) -> Optional[Dict]:
        return self._store.get_document_artifact(document_id, artifact_type)
