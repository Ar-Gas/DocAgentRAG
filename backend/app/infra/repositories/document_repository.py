from pathlib import Path
from typing import Any, Dict, List, Optional

from app.infra.metadata_store import DocumentMetadataStore, get_metadata_store


class DocumentRepository:
    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self._store = get_metadata_store(data_dir=data_dir, db_path=db_path)

    def upsert(self, doc_info: Dict[str, Any]) -> bool:
        return self._store.upsert_document(doc_info)

    def get(self, document_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get_document(document_id)

    def list_all(self) -> List[Dict[str, Any]]:
        return self._store.list_documents()

    def delete(self, document_id: str) -> bool:
        return self._store.delete_document(document_id)

    def update(self, document_id: str, updated_fields: Dict[str, Any]) -> bool:
        return self._store.update_document(document_id, updated_fields)

    def list_by_classification(self, classification: str) -> List[Dict[str, Any]]:
        return self._store.list_by_classification(classification)

    def save_classification_result(self, document_id: str, classification_result: str) -> bool:
        return self._store.save_classification_result(document_id, classification_result)

    def update_status(
        self,
        document_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        return self._store.update_document_status(document_id, status=status, error_message=error_message)
