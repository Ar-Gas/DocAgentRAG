from pathlib import Path
from typing import Dict, Optional

from app.infra.metadata_store import get_metadata_store


class RuntimeArtifactRepository:
    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self._store = get_metadata_store(data_dir=data_dir, db_path=db_path)

    def save(self, name: str, payload: Dict) -> bool:
        return self._store.save_artifact(name, payload)

    def load(self, name: str) -> Optional[Dict]:
        return self._store.load_artifact(name)
