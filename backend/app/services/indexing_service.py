import json
from datetime import datetime, timezone
from typing import Any, Dict

from utils.block_extractor import extract_structured_blocks
from utils.storage import (
    get_block_collection,
    get_document_info,
    update_document_info,
    upsert_document_artifact,
)


class IndexingService:
    READER_ARTIFACT_TYPE = "reader_blocks"

    def index_document(self, document_id: str, force: bool = False) -> Dict[str, Any]:
        doc_info = get_document_info(document_id)
        if not doc_info:
            return {"document_id": document_id, "block_index_status": "failed", "error": "document not found"}

        try:
            block_payload = extract_structured_blocks(doc_info.get("filepath", ""), document_id)
            block_collection = get_block_collection()
            if block_collection is None:
                raise RuntimeError("block collection unavailable")

            old_entries = block_collection.get(where={"document_id": document_id}, include=[])
            old_ids = old_entries.get("ids") or []
            if old_ids:
                block_collection.delete(ids=old_ids)

            blocks = block_payload.get("blocks") or []
            ids = []
            documents = []
            metadatas = []
            indexed_at = datetime.now(timezone.utc).isoformat()

            for index, block in enumerate(blocks):
                block_id = block.get("block_id") or f"{document_id}:{block_payload.get('index_version', 'block-v1')}:{index}"
                ids.append(block_id)
                documents.append(block.get("text", ""))
                metadatas.append(self._build_block_metadata(doc_info, block_payload, block, document_id, indexed_at))

            if ids:
                block_collection.add(documents=documents, metadatas=metadatas, ids=ids)

            upsert_document_artifact(
                document_id,
                self.READER_ARTIFACT_TYPE,
                {
                    "index_version": block_payload.get("index_version"),
                    "indexed_content_hash": block_payload.get("indexed_content_hash"),
                    "block_count": len(blocks),
                    "blocks": blocks,
                },
            )

            update_document_info(
                document_id,
                {
                    "block_index_status": "ready",
                    "index_version": block_payload.get("index_version"),
                    "indexed_content_hash": block_payload.get("indexed_content_hash"),
                    "block_count": len(blocks),
                    "last_indexed_at": indexed_at,
                    "block_index_error": None,
                },
            )
            return {"document_id": document_id, "block_index_status": "ready"}
        except Exception as exc:
            short_error = self._short_error(exc)
            update_document_info(
                document_id,
                {
                    "block_index_status": "failed",
                    "block_index_error": short_error,
                    "last_indexed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return {"document_id": document_id, "block_index_status": "failed", "error": short_error}

    def _build_block_metadata(
        self,
        doc_info: Dict[str, Any],
        block_payload: Dict[str, Any],
        block: Dict[str, Any],
        document_id: str,
        indexed_at: str,
    ) -> Dict[str, Any]:
        heading_path = block.get("heading_path") or []
        page_number = block.get("page_number")

        metadata: Dict[str, Any] = {
            "document_id": document_id,
            "filename": doc_info.get("filename", ""),
            "file_type": doc_info.get("file_type", ""),
            "file_type_family": self._derive_file_type_family(doc_info.get("file_type", "")),
            "source_parser": self._derive_source_parser(doc_info),
            "index_version": block_payload.get("index_version", ""),
            "indexed_content_hash": block_payload.get("indexed_content_hash", ""),
            "block_id": block.get("block_id", ""),
            "block_index": int(block.get("block_index", 0)),
            "block_type": block.get("block_type", "paragraph"),
            "heading_path": json.dumps(heading_path, ensure_ascii=False),
            "page_number": int(page_number) if isinstance(page_number, int) else -1,
            "last_indexed_at": indexed_at,
        }
        return metadata

    @staticmethod
    def _derive_file_type_family(file_type: str) -> str:
        ext = (file_type or "").lower().lstrip(".")
        family_map = {
            "pdf": "pdf",
            "doc": "word",
            "docx": "word",
            "ppt": "presentation",
            "pptx": "presentation",
            "xls": "spreadsheet",
            "xlsx": "spreadsheet",
            "csv": "spreadsheet",
            "txt": "text",
            "md": "text",
            "html": "web",
            "htm": "web",
            "eml": "email",
            "msg": "email",
        }
        return family_map.get(ext, "other")

    @staticmethod
    def _derive_source_parser(doc_info: Dict[str, Any]) -> str:
        parser_name = (doc_info.get("parser_name") or "").strip()
        if parser_name:
            return parser_name
        file_type = (doc_info.get("file_type") or "").strip().lstrip(".")
        if file_type:
            return file_type.lower()
        return "unknown"

    @staticmethod
    def _short_error(exc: Exception, max_len: int = 160) -> str:
        raw = str(exc).strip() or exc.__class__.__name__
        return raw[:max_len]
