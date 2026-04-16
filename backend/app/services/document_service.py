import os
import re
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.infra.file_utils import enrich_document_file_state as _enrich_document_file_state
from app.infra.repositories.document_artifact_repository import DocumentArtifactRepository
from app.infra.repositories.document_content_repository import DocumentContentRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from app.infra.vector_store import get_block_collection
from app.services.document_vector_index_service import DocumentVectorIndexService
from app.services.errors import AppServiceError
from app.services.extraction_service import ExtractionService
from app.services.indexing_service import IndexingService
from config import ALLOWED_EXTENSIONS, BASE_DIR, DATA_DIR, DOC_DIR, EXTENSION_TO_DIR, MAX_FILE_SIZE
from utils.retriever import get_query_parser
from utils.search_cache import get_search_cache

logger = logging.getLogger(__name__)


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def _content_repository() -> DocumentContentRepository:
    return DocumentContentRepository(data_dir=DATA_DIR)


def _segment_repository() -> DocumentSegmentRepository:
    return DocumentSegmentRepository(data_dir=DATA_DIR)


def _artifact_repository() -> DocumentArtifactRepository:
    return DocumentArtifactRepository(data_dir=DATA_DIR)


def _vector_index_service() -> DocumentVectorIndexService:
    return DocumentVectorIndexService(
        document_repository=_document_repository(),
        content_repository=_content_repository(),
        segment_repository=_segment_repository(),
    )


def get_document_info(document_id: str):
    return _document_repository().get(document_id)


def get_all_documents():
    return _document_repository().list_all()


def update_document_info(document_id: str, updated_info: Dict) -> bool:
    return _document_repository().update(document_id, updated_info)


def save_classification_result(document_id: str, classification_result: str) -> bool:
    return _document_repository().save_classification_result(document_id, classification_result)


def get_document_content_record(document_id: str):
    return _content_repository().get(document_id)


def list_document_segments(document_id: str):
    return _segment_repository().list(document_id)


def list_document_artifacts(document_id: str, artifact_type: Optional[str] = None):
    return _artifact_repository().list(document_id, artifact_type)


def get_document_artifact(document_id: str, artifact_type: str):
    return _artifact_repository().get(document_id, artifact_type)


def enrich_document_file_state(doc_info: Optional[Dict], persist: bool = True) -> Dict:
    return _enrich_document_file_state(
        doc_info,
        base_dir=BASE_DIR,
        doc_dir=DOC_DIR,
        get_document_info=get_document_info,
        update_document_info=update_document_info,
        persist=persist,
    )


def save_document_summary_for_classification(
    filepath,
    full_content: Optional[str] = None,
    parser_name: Optional[str] = None,
    display_filename: Optional[str] = None,
):
    return _vector_index_service().save_document_summary_for_classification(
        filepath,
        full_content=full_content,
        parser_name=parser_name,
        display_filename=display_filename,
    )


def delete_document(document_id: str) -> bool:
    _delete_document_blocks(document_id)
    return _document_repository().delete(document_id)


def _delete_document_blocks(document_id: str) -> None:
    collection = get_block_collection()
    if collection is None or not document_id:
        return

    try:
        results = collection.get(where={"document_id": document_id})
        ids = list((results or {}).get("ids") or [])
        if ids:
            collection.delete(ids=ids)
    except Exception as exc:
        logger.warning("删除文档 block 失败: %s", exc)


def _count_blocks(document_id: str) -> int:
    collection = get_block_collection()
    if collection is not None:
        try:
            results = collection.get(where={"document_id": document_id})
            return len((results or {}).get("ids") or [])
        except Exception as exc:
            logger.warning("统计 block 数量失败: %s", exc)

    artifact = get_document_artifact(document_id, "reader_blocks") or {}
    return len(((artifact.get("payload") or {}).get("blocks")) or [])


def get_block_status(document_id: str) -> Dict:
    doc_info = get_document_info(document_id)
    if not doc_info:
        return {
            "document_id": document_id,
            "exists": False,
            "has_blocks": False,
            "block_count": 0,
            "block_index_status": None,
            "chunk_count": 0,
            "has_chunks": False,
            "chunk_info": None,
            "in_sync": False,
        }

    block_count = _count_blocks(document_id)
    expected_block_count = doc_info.get("block_count")
    in_sync = expected_block_count is None or expected_block_count == block_count
    status = doc_info.get("block_index_status")

    return {
        "document_id": document_id,
        "exists": True,
        "has_blocks": block_count > 0,
        "block_count": block_count,
        "expected_block_count": expected_block_count,
        "block_index_status": status,
        "index_version": doc_info.get("index_version"),
        "indexed_content_hash": doc_info.get("indexed_content_hash"),
        "last_indexed_at": doc_info.get("last_indexed_at"),
        "block_index_error": doc_info.get("block_index_error"),
        "chunk_count": block_count,
        "has_chunks": block_count > 0,
        "chunk_info": None,
        "in_sync": in_sync,
    }


class DocumentService:
    def __init__(self):
        self.extraction_service = ExtractionService()
        self.indexing_service = IndexingService()

    @staticmethod
    def _hydrate_document(doc_info: Dict) -> Dict:
        return enrich_document_file_state(doc_info, persist=True)

    def upload(self, filename: str, file_stream) -> Dict:
        # 0.1 路径遍历防护：只取纯文件名，剥离任何目录部分
        safe_name = Path(filename).name
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise AppServiceError(2001, f"不支持的文件类型，仅支持：{', '.join(ALLOWED_EXTENSIONS)}")

        type_subdir = EXTENSION_TO_DIR.get(ext, "other")
        target_dir = DOC_DIR / type_subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        # 实际存储使用 UUID 文件名，保留原始扩展名；metadata 保留原始 safe_name 供展示
        import uuid as _uuid
        stored_stem = _uuid.uuid4().hex
        file_path = target_dir / f"{stored_stem}{ext}"
        counter = 1
        while file_path.exists():
            file_path = target_dir / f"{stored_stem}_{counter}{ext}"
            counter += 1

        # 流式写入磁盘，不一次性读入内存（支持大文件）
        try:
            with open(file_path, "wb") as handle:
                shutil.copyfileobj(file_stream, handle)
        except Exception as e:
            if file_path.exists():
                os.remove(file_path)
            raise AppServiceError(1002, f"文件保存失败: {e}")

        # 写入后再校验大小
        if file_path.stat().st_size > MAX_FILE_SIZE:
            os.remove(file_path)
            raise AppServiceError(2002, f"文件过大，最大支持{MAX_FILE_SIZE // 1024 // 1024}MB")

        extraction = self.extraction_service.extract(str(file_path))
        if not extraction.success:
            if file_path.exists():
                os.remove(file_path)
            raise AppServiceError(1002, extraction.error or "文档解析失败，请检查文件是否损坏或格式是否正确")

        document_id, doc_info = save_document_summary_for_classification(
            str(file_path),
            full_content=extraction.content,
            parser_name=extraction.parser_name,
            display_filename=safe_name,
        )
        if not document_id:
            if file_path.exists():
                os.remove(file_path)
            raise AppServiceError(1002, "文档解析失败，请检查文件是否损坏或格式是否正确")

        indexing_result = self.indexing_service.index_document(document_id, force=True)
        if (indexing_result or {}).get("block_index_status") != "ready":
            delete_document(document_id)
            if file_path.exists():
                os.remove(file_path)
            detail = (indexing_result or {}).get("error") or "block 索引构建失败"
            raise AppServiceError(1003, f"文档索引失败: {detail}")

        # 3.1/3.2 新文档入库后使搜索缓存失效
        try:
            get_search_cache().invalidate_all()
        except Exception:
            pass

        try:
            from app.services.classification_service import ClassificationService

            ClassificationService().classify(document_id)
            refreshed = get_document_info(document_id) or doc_info
            doc_info = {**doc_info, **refreshed}
        except Exception:
            pass  # 主题归类失败不影响上传主流程

        return self._hydrate_document(doc_info)

    def list_documents(self, page: int, page_size: int) -> Dict:
        all_docs = get_all_documents()
        total = len(all_docs)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": [self._hydrate_document(item) for item in all_docs[start:end]],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        }

    def get_document(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")
        return self._hydrate_document(doc_info)

    def get_document_payload(self, document_id: str) -> Dict:
        doc_info = self.get_document(document_id)
        content_record = get_document_content_record(document_id) or {}
        segments = list_document_segments(document_id)
        artifacts = list_document_artifacts(document_id)
        return {
            **doc_info,
            "content_record": content_record,
            "segments": segments,
            "artifacts": artifacts,
        }

    def get_reader_payload(
        self,
        document_id: str,
        query: str = "",
        anchor_block_id: Optional[str] = None,
    ) -> Dict:
        doc_info = self.get_document(document_id)
        content_record = get_document_content_record(document_id) or {}
        blocks = self._build_reader_blocks(document_id, content_record)
        keywords = self._extract_reader_terms(query)

        total_matches = 0
        resolved_anchor = {
            "block_id": anchor_block_id,
            "block_index": 0,
            "match_index": 0,
            "start": 0,
            "end": 0,
            "term": keywords[0] if keywords else None,
        }
        resolved_anchor_score = (-1, -1)
        hydrated_blocks = []

        for block in blocks:
            matches = self._find_text_matches(block["text"], keywords)
            total_matches += len(matches)
            block_payload = {**block, "matches": matches}
            hydrated_blocks.append(block_payload)

            anchor_score = (len(matches), -block["block_index"])
            should_replace_anchor = False
            if anchor_block_id and block["block_id"] == anchor_block_id:
                should_replace_anchor = True
            elif not anchor_block_id and matches and anchor_score > resolved_anchor_score:
                should_replace_anchor = True

            if should_replace_anchor:
                first_match = matches[0] if matches else {"start": 0, "end": 0, "term": None}
                resolved_anchor = {
                    "block_id": block["block_id"],
                    "block_index": block["block_index"],
                    "match_index": 0,
                    "start": first_match["start"],
                    "end": first_match["end"],
                    "term": first_match["term"],
                }
                resolved_anchor_score = anchor_score

        if not resolved_anchor.get("block_id") and hydrated_blocks:
            first_block = hydrated_blocks[0]
            resolved_anchor["block_id"] = first_block["block_id"]
            resolved_anchor["block_index"] = first_block["block_index"]

        return {
            "document_id": document_id,
            "filename": doc_info.get("filename", ""),
            "file_type": doc_info.get("file_type", ""),
            "classification_result": doc_info.get("classification_result"),
            "created_at_iso": doc_info.get("created_at_iso"),
            "parser_name": content_record.get("parser_name") or doc_info.get("parser_name"),
            "extraction_status": content_record.get("extraction_status") or doc_info.get("extraction_status"),
            "query": query or "",
            "keywords": keywords,
            "total_matches": total_matches,
            "best_anchor": resolved_anchor,
            "blocks": hydrated_blocks,
        }

    def delete_document(self, document_id: str) -> Dict:
        doc_info = self.get_document(document_id)
        file_path = Path(doc_info.get("filepath", ""))
        file_deleted = False

        try:
            if file_path.exists():
                os.remove(file_path)
            file_deleted = True
        except Exception:
            file_deleted = True

        if not delete_document(document_id):
            raise AppServiceError(1004, f"文档ID: {document_id}")

        # 3.1/3.2 删除文档后使搜索缓存失效
        try:
            get_search_cache().invalidate_all()
        except Exception:
            pass

        return {"document_id": document_id, "file_deleted": file_deleted}

    def rechunk(self, document_id: str, use_refiner: bool) -> Dict:
        self.get_document(document_id)
        _ = use_refiner
        result = self.indexing_service.index_document(document_id, force=True)
        if (result or {}).get("block_index_status") != "ready":
            raise AppServiceError(1003, (result or {}).get("error", "重新构建 block 索引失败"))
        return get_block_status(document_id)

    def get_chunk_status(self, document_id: str) -> Dict:
        chunk_status = get_block_status(document_id)
        if not chunk_status.get("exists"):
            raise AppServiceError(1001, f"文档ID: {document_id}")
        return chunk_status

    def batch_rechunk(self, document_ids: List[str], use_refiner: bool) -> Dict:
        results = []
        _ = use_refiner
        for document_id in document_ids:
            try:
                self.get_document(document_id)
                result = self.indexing_service.index_document(document_id, force=True)
                success = (result or {}).get("block_index_status") == "ready"
                payload = {"document_id": document_id, "success": success}
                if not success and (result or {}).get("error"):
                    payload["error"] = result["error"]
                results.append(payload)
            except Exception as exc:
                results.append({"document_id": document_id, "success": False, "error": str(exc)})

        success_count = sum(1 for item in results if item["success"])
        return {"results": results, "total": len(results), "success_count": success_count}

    def _build_reader_blocks(self, document_id: str, content_record: Dict) -> List[Dict]:
        artifact = get_document_artifact(document_id, "reader_blocks") or {}
        artifact_blocks = (artifact.get("payload") or {}).get("blocks") or []
        if artifact_blocks:
            return [
                {
                    "block_id": block.get("block_id") or f"{document_id}#{block.get('block_index', index)}",
                    "block_index": block.get("block_index", index),
                    "block_type": block.get("block_type") or "paragraph",
                    "heading_path": list(block.get("heading_path") or []),
                    "page_number": block.get("page_number"),
                    "text": block.get("text", ""),
                }
                for index, block in enumerate(sorted(artifact_blocks, key=lambda item: item.get("block_index", 0)))
                if block.get("text")
            ]

        segments = list_document_segments(document_id)
        if segments:
            return [
                {
                    "block_id": segment.get("segment_id") or f"{document_id}#{segment.get('segment_index', index)}",
                    "block_index": segment.get("segment_index", index),
                    "block_type": "paragraph",
                    "heading_path": [segment.get("title")] if segment.get("title") else [],
                    "text": segment.get("content", ""),
                    "page_number": segment.get("page_number"),
                }
                for index, segment in enumerate(segments)
                if segment.get("content")
            ]

        full_content = content_record.get("full_content") or content_record.get("preview_content") or ""
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n|\n", full_content) if item.strip()]
        if not paragraphs and full_content.strip():
            paragraphs = [full_content.strip()]

        return [
            {
                "block_id": f"{document_id}#{index}",
                "block_index": index,
                "block_type": "paragraph",
                "heading_path": [],
                "text": paragraph,
                "page_number": None,
            }
            for index, paragraph in enumerate(paragraphs)
        ]

    def _extract_reader_terms(self, query: str) -> List[str]:
        if not query or not query.strip():
            return []

        parser = get_query_parser()
        parsed = parser.parse(query)
        ordered_terms: List[str] = []
        for item in [*parsed.exact_phrases, *parsed.include_terms, *parsed.fuzzy_terms]:
            value = (item or "").strip()
            if value and value not in ordered_terms:
                ordered_terms.append(value)

        normalized_query = query.strip()
        if normalized_query and normalized_query not in ordered_terms:
            ordered_terms.append(normalized_query)
        return sorted(ordered_terms, key=len, reverse=True)

    @staticmethod
    def _find_text_matches(text: str, terms: List[str]) -> List[Dict]:
        if not text or not terms:
            return []

        matches: List[Dict] = []
        for term in terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            for item in pattern.finditer(text):
                candidate = {
                    "start": item.start(),
                    "end": item.end(),
                    "term": term,
                }
                if any(
                    existing["start"] == candidate["start"] and existing["end"] == candidate["end"]
                    for existing in matches
                ):
                    continue
                matches.append(candidate)
        matches.sort(key=lambda item: (item["start"], -(item["end"] - item["start"])))
        return matches
