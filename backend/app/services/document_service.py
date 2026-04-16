import os
import re
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.services.errors import AppServiceError
from app.services.extraction_service import ExtractionService
from app.services.indexing_service import IndexingService
from config import ALLOWED_EXTENSIONS, EXTENSION_TO_DIR, MAX_FILE_SIZE
from utils.retriever import get_query_parser, get_bm25_service
from utils.search_cache import get_search_cache
from utils.storage import (
    DOC_DIR,
    check_document_chunks,
    delete_document,
    enrich_document_file_state,
    get_document_artifact,
    get_document_content_record,
    get_all_documents,
    get_document_info,
    list_document_artifacts,
    list_document_segments,
    re_chunk_document,
    save_document_summary_for_classification,
    save_document_to_chroma,
    update_document_info,
)

logger = logging.getLogger(__name__)


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

        save_success = save_document_to_chroma(
            str(file_path),
            document_id=document_id,
            full_content=extraction.content,
        )
        if not save_success:
            delete_document(document_id)
            if file_path.exists():
                os.remove(file_path)
            raise AppServiceError(1003, "文档存入向量库失败，请检查后端日志了解详细原因")

        # 3.1/3.2 新文档入库后使 BM25 索引和搜索缓存失效
        try:
            get_bm25_service().invalidate()
            get_search_cache().invalidate_all()
        except Exception:
            pass

        # B. 上传完成后自动分类，失败不影响上传结果
        try:
            from utils.classifier import classify_document
            from utils.storage import save_classification_result
            classification_result = classify_document(doc_info)
            if classification_result:
                result_data = classification_result.get("classification_result", {})
                categories = result_data.get("categories", [])
                actual_path = result_data.get("actual_path")
                if categories:
                    save_classification_result(document_id, categories[0])
                    doc_info["classification_result"] = categories[0]
                if actual_path:
                    update_document_info(document_id, {"filepath": actual_path})
                    doc_info["filepath"] = actual_path
        except Exception:
            pass  # 分类失败不报错，仅记录到日志

        self._trigger_block_reindex_best_effort(document_id, context="upload")
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

        # 3.1/3.2 删除文档后使 BM25 索引和搜索缓存失效
        try:
            get_bm25_service().invalidate()
            get_search_cache().invalidate_all()
        except Exception:
            pass

        return {"document_id": document_id, "file_deleted": file_deleted}

    def rechunk(self, document_id: str, use_refiner: bool) -> Dict:
        self.get_document(document_id)
        success = re_chunk_document(document_id, use_refiner=use_refiner)
        if not success:
            raise AppServiceError(1003, "重新分片失败")
        self._trigger_block_reindex_best_effort(document_id, context="rechunk")
        return check_document_chunks(document_id)

    def get_chunk_status(self, document_id: str) -> Dict:
        chunk_status = check_document_chunks(document_id)
        if not chunk_status.get("exists"):
            raise AppServiceError(1001, f"文档ID: {document_id}")
        return chunk_status

    def batch_rechunk(self, document_ids: List[str], use_refiner: bool) -> Dict:
        results = []
        for document_id in document_ids:
            try:
                success = re_chunk_document(document_id, use_refiner=use_refiner)
                results.append({"document_id": document_id, "success": success})
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

    def _trigger_block_reindex_best_effort(self, document_id: str, context: str) -> None:
        try:
            self.indexing_service.index_document(document_id, force=True)
        except Exception as exc:
            logger.warning("block reindex best-effort failed during %s for %s: %s", context, document_id, exc)

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
