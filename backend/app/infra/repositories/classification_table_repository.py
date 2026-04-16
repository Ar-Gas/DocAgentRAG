from pathlib import Path
from typing import Dict, List, Optional

from app.infra.metadata_store import get_metadata_store


class ClassificationTableRepository:
    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self._store = get_metadata_store(data_dir=data_dir, db_path=db_path)

    def save(self, table_payload: Dict, table_id: Optional[str] = None) -> str:
        return self._store.save_classification_table(table_payload, table_id)

    def get(self, table_id: str) -> Optional[Dict]:
        return self._store.get_classification_table(table_id)

    def list(self, limit: int = 50) -> List[Dict]:
        return self._store.list_classification_tables(limit)
