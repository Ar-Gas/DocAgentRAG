from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.errors import AppServiceError
from utils.logger import get_logger, log_retrieval
from utils.search_cache import get_search_cache
from utils.retriever import (
    batch_search_documents,
    get_document_by_id,
    get_document_stats,
    get_ready_block_document_ids,
    get_query_parser,
    hybrid_search,
    keyword_search,
    multimodal_search,
    search_block_documents,
    search_documents,
    search_with_highlight,
)
from utils.smart_retrieval import (
    expand_query_keywords,
    expand_query_with_llm,
    is_llm_available,
    smart_retrieval,
    summarize_retrieval_results,
)
from utils.storage import (
    enrich_document_file_state,
    get_all_documents,
    get_document_content_record,
    get_document_info,
    list_document_segments,
)


class RetrievalService:
    def search(self, query: str, limit: int, use_rerank: bool, file_types: Optional[List[str]] = None) -> Dict:
        self._ensure_query(query)
        results = search_documents(query, limit=limit, use_rerank=use_rerank, file_types=file_types)
        return {"query": query, "total": len(results), "results": results}

    def hybrid(self, query: str, limit: int, alpha: float, use_rerank: bool, file_types: Optional[List[str]] = None) -> Dict:
        self._ensure_query(query)
        results = hybrid_search(query=query, limit=limit, alpha=alpha, use_rerank=use_rerank, file_types=file_types)
        return {"query": query, "total": len(results), "alpha": alpha, "results": results}

    def keyword(self, query: str, limit: int, file_types: Optional[List[str]] = None) -> Dict:
        self._ensure_query(query)
        results = keyword_search(query=query, limit=limit, file_types=file_types)
        return {"query": query, "total": len(results), "results": results}

    def smart(self, query: str, limit: int, use_query_expansion: bool, use_llm_rerank: bool, expansion_method: str, file_types: Optional[List[str]] = None) -> Dict:
        self._ensure_query(query)

        def search_wrapper(expanded_query: str, limit: int = 10):
            return hybrid_search(
                query=expanded_query,
                limit=limit,
                alpha=0.5,
                use_rerank=False,
                file_types=file_types,
            )

        results, meta_info = smart_retrieval(
            query=query,
            search_func=search_wrapper,
            limit=limit,
            use_query_expansion=use_query_expansion,
            use_llm_rerank=use_llm_rerank,
            expansion_method=expansion_method,
        )
        return {
            "query": query,
            "total": len(results),
            "results": results,
            "meta": {
                "expanded_queries": meta_info["expanded_queries"],
                "expansion_method": meta_info["expansion_method"],
                "rerank_method": meta_info["rerank_method"],
                "total_candidates": meta_info["total_candidates"],
            },
        }

    def batch(self, queries: List[str], limit: int) -> Dict:
        if not queries:
            raise AppServiceError(3002, "查询列表不能为空")
        results = batch_search_documents(queries, limit=limit)
        return {
            "total_queries": len(queries),
            "batch_results": [
                {"query": query, "total": len(results[index]) if index < len(results) else 0, "results": results[index] if index < len(results) else []}
                for index, query in enumerate(queries)
            ],
        }

    def get_document_chunks(self, document_id: str) -> Dict:
        result = get_document_by_id(document_id)
        if not result:
            raise AppServiceError(1001, f"文档ID: {document_id}")
        chunks = result.get("chunks", [])
        metadatas = result.get("metadatas", [])
        ids = result.get("ids", [])
        return {
            "document_id": document_id,
            "total_chunks": len(chunks),
            "chunks": [
                {
                    "chunk_id": chunk_id,
                    "chunk_index": index,
                    "content": chunk[:500] + "..." if len(chunk) > 500 else chunk,
                    "full_length": len(chunk),
                    "metadata": metadata,
                }
                for index, (chunk, metadata, chunk_id) in enumerate(zip(chunks, metadatas, ids))
            ],
        }

    def stats(self) -> Dict:
        stats = get_document_stats()
        all_docs = get_all_documents()
        segment_document_ids = {
            doc.get("id")
            for doc in all_docs
            if doc.get("id") and list_document_segments(doc.get("id"))
        }
        return {
            "total_documents": len(all_docs),
            "vector_indexed_documents": stats.get("vector_indexed_documents", 0),
            "segment_documents": len(segment_document_ids),
            "total_chunks": stats.get("total_chunks", 0),
            "file_types": stats.get("file_types", {}),
        }

    def expand_query(self, query: str, method: str) -> Dict:
        self._ensure_query(query)
        if method == "llm" and not is_llm_available():
            return {
                "query": query,
                "method": "keyword_fallback",
                "expanded_queries": expand_query_keywords(query),
                "llm_available": False,
            }

        expanded_queries = expand_query_with_llm(query) if method == "llm" else expand_query_keywords(query)
        return {
            "query": query,
            "method": method,
            "expanded_queries": expanded_queries,
            "llm_available": is_llm_available(),
        }

    def llm_status(self) -> Dict:
        import os

        doubao_key = os.environ.get("DOUBAO_API_KEY", "")
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        return {
            "llm_available": is_llm_available(),
            "provider": "doubao" if doubao_key else ("openai" if openai_key else None),
            "doubao_configured": bool(doubao_key),
            "doubao_model": os.environ.get("DOUBAO_LLM_MODEL", "doubao-pro-32k-241115"),
            "openai_configured": bool(openai_key),
            "openai_base_url": os.environ.get("OPENAI_BASE_URL", "未配置"),
            "openai_model": os.environ.get("LLM_MODEL", "未配置"),
        }

    def multimodal(self, query: str, image_url: Optional[str], limit: int, file_types: Optional[List[str]] = None) -> Dict:
        if not query and not image_url:
            raise AppServiceError(3002, "查询文本和图片URL至少需要提供一个")
        results = multimodal_search(query=query, image_url=image_url, limit=limit, file_types=file_types)
        return {"query": query, "has_image": bool(image_url), "total": len(results), "results": results}

    def search_highlight(self, query: str, search_type: str, limit: int, alpha: float, use_rerank: bool, file_types: Optional[List[str]] = None) -> Dict:
        self._ensure_query(query)
        results, meta_info = search_with_highlight(
            query=query,
            search_type=search_type,
            limit=limit,
            alpha=alpha,
            use_rerank=use_rerank,
            file_types=file_types,
        )
        return {
            "query": query,
            "search_type": search_type,
            "total": len(results),
            "keywords": meta_info.get("keywords", []),
            "results": results,
        }

    def summarize_results(self, query: str, results: List[Dict]) -> Dict:
        self._ensure_query(query)
        return summarize_retrieval_results(query, results)

    @log_retrieval
    def workspace_search(
        self,
        query: str = "",
        mode: str = "hybrid",
        retrieval_version: Optional[str] = None,
        limit: int = 10,
        alpha: float = 0.5,
        use_rerank: bool = False,
        use_query_expansion: bool = True,
        use_llm_rerank: bool = True,
        expansion_method: str = "llm",
        file_types: Optional[List[str]] = None,
        filename: Optional[str] = None,
        classification: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        group_by_document: bool = True,
    ) -> Dict[str, Any]:
        normalized_query = (query or "").strip()
        normalized_mode = self._normalize_workspace_mode(mode)
        requested_retrieval_version = self._resolve_requested_retrieval_version(retrieval_version)
        normalized_limit = max(1, min(limit, 100))
        normalized_file_types = self._normalize_file_types(file_types)
        applied_filters = {
            "file_types": normalized_file_types,
            "filename": filename or None,
            "classification": classification or None,
            "date_from": date_from or None,
            "date_to": date_to or None,
            "group_by_document": group_by_document,
        }

        # 3.2 LRU 缓存：相同参数直接返回
        _cache = get_search_cache()
        _filter_key = {
            "retrieval_version": requested_retrieval_version,
            "file_types": sorted(normalized_file_types or []),
            "filename": filename or "",
            "classification": classification or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
            "alpha": alpha,
            "use_rerank": use_rerank,
            "use_query_expansion": use_query_expansion,
            "use_llm_rerank": use_llm_rerank,
            "expansion_method": expansion_method or "",
            "group_by_document": group_by_document,
        }
        cached = _cache.get(normalized_query, normalized_mode, _filter_key)
        if cached is not None:
            return cached

        if requested_retrieval_version == "block":
            ready_document_ids = get_ready_block_document_ids(
                file_types=normalized_file_types,
                filename=filename,
                classification=classification,
                date_from=date_from,
                date_to=date_to,
            )
            if ready_document_ids:
                block_payload = search_block_documents(
                    query=normalized_query,
                    mode=normalized_mode,
                    limit=normalized_limit,
                    alpha=alpha,
                    use_rerank=use_rerank,
                    use_llm_rerank=use_llm_rerank,
                    file_types=normalized_file_types,
                    classification=classification,
                    date_from=date_from,
                    date_to=date_to,
                    ready_document_ids=ready_document_ids,
                    group_by_document=group_by_document,
                    use_query_expansion=use_query_expansion,
                    expansion_method=expansion_method,
                )
                documents = list(block_payload.get("documents") or [])
                results = list(block_payload.get("results") or [])
                if group_by_document:
                    documents = documents[:normalized_limit]
                    results = self._flatten_surfaced_block_results(documents)
                else:
                    results = results[:normalized_limit]
                result = {
                    "query": normalized_query,
                    "mode": normalized_mode,
                    "retrieval_version_requested": requested_retrieval_version,
                    "retrieval_version_used": "block",
                    "total_results": len(results),
                    "total_documents": len(documents),
                    "results": results,
                    "documents": documents,
                    "meta": block_payload.get("meta") or {"fallback_used": False},
                    "applied_filters": applied_filters,
                }
                _cache.set(normalized_query, normalized_mode, _filter_key, result)
                return result
            block_meta: Dict[str, Any] = {
                "fallback_used": True,
                "fallback_reason": "no_ready_block_documents",
                "fallback_documents": [],
            }
        else:
            block_meta = {}

        raw_results: List[Dict[str, Any]] = []
        meta: Dict[str, Any] = {}
        if normalized_query:
            raw_results, meta = self._run_workspace_query_search(
                query=normalized_query,
                mode=normalized_mode,
                limit=normalized_limit * 3,
                alpha=alpha,
                use_rerank=use_rerank,
                use_query_expansion=use_query_expansion,
                use_llm_rerank=use_llm_rerank,
                expansion_method=expansion_method,
                file_types=normalized_file_types,
            )
            fallback_results = self._search_workspace_metadata(
                query=normalized_query,
                file_types=normalized_file_types,
                limit=normalized_limit * 2,
            )
            raw_results = self._merge_workspace_results(raw_results, fallback_results)
            if fallback_results:
                meta = {
                    **meta,
                    "metadata_fallback_used": True,
                    "metadata_fallback_count": len(fallback_results),
                }
        else:
            raw_results = self._build_metadata_only_results()

        filtered_results: List[Dict[str, Any]] = []
        for result in raw_results:
            hydrated = self._hydrate_workspace_result(result)
            if hydrated and self._matches_workspace_filters(
                hydrated,
                file_types=normalized_file_types,
                filename=filename,
                classification=classification,
                date_from=date_from,
                date_to=date_to,
            ):
                filtered_results.append(hydrated)

        filtered_results.sort(
            key=lambda item: (
                item.get("similarity", 0),
                item.get("created_at_iso") or "",
            ),
            reverse=True,
        )
        filtered_results = filtered_results[:normalized_limit]

        documents = self._group_workspace_results(filtered_results, normalized_query)
        result = {
            "query": normalized_query,
            "mode": normalized_mode,
            "retrieval_version_requested": requested_retrieval_version,
            "retrieval_version_used": "legacy",
            "total_results": len(filtered_results),
            "total_documents": len(documents),
            "results": filtered_results,
            "documents": documents,
            "meta": {**meta, **block_meta},
            "applied_filters": applied_filters,
        }
        # 3.2 写入缓存（smart 模式 LLM rerank 结果也缓存）
        _cache.set(normalized_query, normalized_mode, _filter_key, result)
        return result

    @staticmethod
    def _ensure_query(query: str) -> None:
        if not query or not query.strip():
            raise AppServiceError(3002, "查询关键词不能为空")

    @staticmethod
    def _normalize_workspace_mode(mode: str) -> str:
        normalized = (mode or "hybrid").strip().lower()
        aliases = {
            "semantic": "vector",
            "vector": "vector",
            "keyword": "keyword",
            "hybrid": "hybrid",
            "smart": "smart",
        }
        return aliases.get(normalized, "hybrid")

    @staticmethod
    def _normalize_file_types(file_types: Optional[List[str]]) -> List[str]:
        if not file_types:
            return []
        normalized = []
        for item in file_types:
            if not item:
                continue
            value = item.strip().lower().lstrip(".")
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    @staticmethod
    def _resolve_requested_retrieval_version(retrieval_version: Optional[str]) -> str:
        normalized = (retrieval_version or "").strip().lower()
        return "block" if normalized == "block" else "legacy"

    @staticmethod
    def _flatten_surfaced_block_results(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        flattened: List[Dict[str, Any]] = []
        for document in documents:
            document_id = document.get("document_id")
            for evidence in document.get("evidence_blocks") or []:
                flattened.append(
                    {
                        "document_id": document_id,
                        "block_id": evidence.get("block_id"),
                        "block_index": evidence.get("block_index", 0),
                        "block_type": evidence.get("block_type", "paragraph"),
                        "snippet": evidence.get("snippet", ""),
                        "heading_path": evidence.get("heading_path", []),
                        "page_number": evidence.get("page_number"),
                        "score": evidence.get("score", 0.0),
                        "match_reason": evidence.get("match_reason", ""),
                    }
                )
        flattened.sort(
            key=lambda item: (
                item.get("score", 0.0),
                -item.get("block_index", 0),
            ),
            reverse=True,
        )
        return flattened

    def _run_workspace_query_search(
        self,
        query: str,
        mode: str,
        limit: int,
        alpha: float,
        use_rerank: bool,
        use_query_expansion: bool,
        use_llm_rerank: bool,
        expansion_method: str,
        file_types: List[str],
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if mode == "keyword":
            return keyword_search(query=query, limit=limit, file_types=file_types), {}
        if mode == "vector":
            return search_documents(query, limit=limit, use_rerank=use_rerank, file_types=file_types), {}
        if mode == "smart":
            result = self.smart(
                query=query,
                limit=limit,
                use_query_expansion=use_query_expansion,
                use_llm_rerank=use_llm_rerank,
                expansion_method=expansion_method,
                file_types=file_types,
            )
            return result.get("results", []), result.get("meta", {})
        return hybrid_search(
            query=query,
            limit=limit,
            alpha=alpha,
            use_rerank=use_rerank,
            file_types=file_types,
        ), {"alpha": alpha}

    def _build_metadata_only_results(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for doc in get_all_documents():
            document_id = doc.get("id")
            if not document_id:
                continue
            content_record = get_document_content_record(document_id) or {}
            segments = list_document_segments(document_id)
            first_segment = segments[0] if segments else {}
            snippet = (
                content_record.get("preview_content")
                or doc.get("preview_content")
                or first_segment.get("content")
                or ""
            )
            results.append(
                {
                    "document_id": document_id,
                    "filename": doc.get("filename", ""),
                    "path": doc.get("filepath", ""),
                    "file_type": doc.get("file_type", ""),
                    "similarity": 1.0,
                    "content_snippet": snippet[:240],
                    "chunk_index": first_segment.get("segment_index", 0),
                }
            )
        return results

    def _search_workspace_metadata(
        self,
        query: str,
        file_types: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        parser = get_query_parser()
        parsed = parser.parse(query)
        search_terms = self._collect_workspace_search_terms(parsed, query)
        results: List[Dict[str, Any]] = []

        for doc in get_all_documents():
            document_id = doc.get("id")
            if not document_id:
                continue

            file_type = (doc.get("file_type") or "").lower().lstrip(".")
            parsed_file_types = [item.lower().lstrip(".") for item in parsed.file_types]
            effective_file_types = list(dict.fromkeys([*file_types, *parsed_file_types]))
            if effective_file_types and file_type not in effective_file_types:
                continue

            content_record = get_document_content_record(document_id) or {}
            segments = list_document_segments(document_id)
            first_segment = segments[0] if segments else {}
            filename = doc.get("filename", "")
            classification = doc.get("classification_result", "")
            preview_content = (
                content_record.get("preview_content")
                or doc.get("preview_content")
                or first_segment.get("content")
                or ""
            )
            full_content = content_record.get("full_content") or ""
            combined_text = "\n".join(
                item
                for item in [filename, classification, preview_content, full_content]
                if item
            )
            if not combined_text.strip():
                continue
            if parser.should_exclude(combined_text, parsed):
                continue

            similarity = self._score_workspace_metadata_match(
                parsed=parsed,
                search_terms=search_terms,
                filename=filename,
                classification=classification,
                preview_content=preview_content,
                full_content=full_content,
            )
            if similarity <= 0:
                continue

            results.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "path": doc.get("filepath", ""),
                    "file_type": doc.get("file_type", ""),
                    "similarity": similarity,
                    "content_snippet": preview_content[:240],
                    "chunk_index": first_segment.get("segment_index", 0),
                }
            )

        results.sort(
            key=lambda item: (
                item.get("similarity", 0),
                item.get("filename", ""),
            ),
            reverse=True,
        )
        return results[:limit]

    @staticmethod
    def _collect_workspace_search_terms(parsed: Any, raw_query: str) -> List[str]:
        terms: List[str] = []
        for item in [*parsed.include_terms, *parsed.exact_phrases, *parsed.fuzzy_terms]:
            normalized = (item or "").strip().lower()
            if normalized and normalized not in terms:
                terms.append(normalized)

        normalized_query = (raw_query or "").strip().lower()
        if normalized_query and normalized_query not in terms:
            terms.append(normalized_query)
        return terms

    @staticmethod
    def _score_workspace_metadata_match(
        parsed: Any,
        search_terms: List[str],
        filename: str,
        classification: str,
        preview_content: str,
        full_content: str,
    ) -> float:
        filename_lower = (filename or "").lower()
        classification_lower = (classification or "").lower()
        preview_lower = (preview_content or "").lower()
        full_lower = (full_content or "").lower()
        combined_lower = "\n".join(item for item in [filename_lower, classification_lower, preview_lower, full_lower] if item)

        if not combined_lower:
            return 0.0

        score = 0.0
        max_score = 0.0

        for phrase in parsed.exact_phrases:
            normalized = phrase.strip().lower()
            if not normalized:
                continue
            max_score += 1.2
            if normalized in filename_lower:
                score += 1.2
            elif normalized in preview_lower or normalized in full_lower:
                score += 1.0
            elif normalized in classification_lower:
                score += 0.8

        for term in search_terms:
            if not term:
                continue
            max_score += 1.0
            if term in filename_lower:
                score += 1.0
            elif term in classification_lower:
                score += 0.85
            elif term in preview_lower:
                score += 0.75
            elif term in full_lower:
                score += 0.55

        if parsed.original_query:
            max_score += 1.0
            original_query = parsed.original_query.lower()
            if original_query in filename_lower:
                score += 1.0
            elif original_query in preview_lower:
                score += 0.9
            elif original_query in full_lower:
                score += 0.7

        if score <= 0 or max_score <= 0:
            return 0.0

        normalized = score / max_score
        if parsed.exact_phrases and not any(
            phrase.strip().lower() in combined_lower for phrase in parsed.exact_phrases
        ):
            normalized *= 0.5
        return round(min(0.99, max(0.1, normalized)), 4)

    @staticmethod
    def _merge_workspace_results(primary: List[Dict[str, Any]], secondary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not primary:
            return list(secondary)
        if not secondary:
            return list(primary)

        merged = list(primary)
        existing_documents = {item.get("document_id") for item in primary if item.get("document_id")}
        for item in secondary:
            if item.get("document_id") not in existing_documents:
                merged.append(item)
        return merged

    def _hydrate_workspace_result(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        document_id = result.get("document_id")
        if not document_id:
            return None

        doc_info = get_document_info(document_id) or {}
        doc_info = enrich_document_file_state(doc_info, persist=True)
        content_record = get_document_content_record(document_id) or {}
        segments = list_document_segments(document_id)
        chunk_index = result.get("chunk_index", 0)
        current_segment = next((item for item in segments if item.get("segment_index") == chunk_index), None)
        preview_content = (
            content_record.get("preview_content")
            or doc_info.get("preview_content")
            or result.get("content_snippet")
            or ""
        )

        return {
            **result,
            "filename": result.get("filename") or doc_info.get("filename", ""),
            "path": doc_info.get("filepath") or result.get("path") or "",
            "file_type": result.get("file_type") or doc_info.get("file_type", ""),
            "classification_result": doc_info.get("classification_result"),
            "file_available": doc_info.get("file_available", False),
            "created_at_iso": doc_info.get("created_at_iso"),
            "parser_name": content_record.get("parser_name") or doc_info.get("parser_name"),
            "extraction_status": content_record.get("extraction_status") or doc_info.get("extraction_status"),
            "preview_content": preview_content,
            "segment_count": len(segments),
            "current_segment": current_segment,
        }

    def _matches_workspace_filters(
        self,
        result: Dict[str, Any],
        file_types: List[str],
        filename: Optional[str],
        classification: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> bool:
        result_file_type = (result.get("file_type") or "").lower().lstrip(".")
        if file_types and result_file_type not in file_types:
            return False

        if filename:
            filename_filter = filename.strip().lower()
            if filename_filter not in (result.get("filename") or "").lower():
                return False

        if classification:
            result_classification = (result.get("classification_result") or "未分类").lower()
            if classification.strip().lower() not in result_classification:
                return False

        created_at = result.get("created_at_iso")
        if date_from and not self._is_on_or_after(created_at, date_from):
            return False
        if date_to and not self._is_on_or_before(created_at, date_to):
            return False

        return True

    def _group_workspace_results(self, results: List[Dict[str, Any]], query: str = "") -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        parser = get_query_parser()
        parsed = parser.parse(query) if query else None
        match_terms = self._collect_workspace_search_terms(parsed, query) if parsed else []

        for result in results:
            document_id = result.get("document_id")
            if not document_id:
                continue

            group = grouped.setdefault(
                document_id,
                {
                    "document_id": document_id,
                    "filename": result.get("filename", ""),
                    "file_type": result.get("file_type", ""),
                    "classification_result": result.get("classification_result"),
                    "file_available": result.get("file_available", False),
                    "created_at_iso": result.get("created_at_iso"),
                    "parser_name": result.get("parser_name"),
                    "extraction_status": result.get("extraction_status"),
                    "preview_content": result.get("preview_content", ""),
                    "path": result.get("path", ""),
                    "score": result.get("similarity", 0),
                    "best_similarity": result.get("similarity", 0),
                    "hit_count": 0,
                    "result_count": 0,
                    "best_excerpt": "",
                    "best_block_id": None,
                    "matched_terms": [],
                    "evidence_blocks": [],
                    "top_segments": [],
                    "results": [],
                },
            )

            group["hit_count"] += 1
            group["result_count"] = group["hit_count"]
            group["score"] = max(group["score"], result.get("similarity", 0))
            group["best_similarity"] = group["score"]
            group["file_available"] = result.get("file_available", group.get("file_available", False))
            group["results"].append(result)

            current_segment = result.get("current_segment")
            block_index = (
                (current_segment or {}).get("segment_index")
                if current_segment
                else result.get("chunk_index", 0)
            )
            block_id = (
                (current_segment or {}).get("segment_id")
                if current_segment
                else f"{document_id}#{block_index}"
            )
            snippet = (
                result.get("content_snippet")
                or (current_segment or {}).get("content")
                or result.get("preview_content", "")
            )
            evidence = {
                "block_id": block_id,
                "block_index": block_index or 0,
                "snippet": snippet or "",
                "score": result.get("similarity", 0),
                "page_number": (current_segment or {}).get("page_number"),
            }
            existing_snippets = {
                (item.get("snippet") or "")[:80]
                for item in group["evidence_blocks"]
            }
            snippet_key = (snippet or "")[:80]
            if block_id and block_id not in {item.get("block_id") for item in group["evidence_blocks"]} and snippet_key not in existing_snippets:
                group["evidence_blocks"].append(evidence)

            if current_segment and current_segment.get("segment_id") not in {
                segment.get("segment_id") for segment in group["top_segments"]
            }:
                group["top_segments"].append(current_segment)

            if snippet:
                normalized_snippet = snippet.lower()
                for term in match_terms:
                    if term and term.lower() in normalized_snippet and term not in group["matched_terms"]:
                        group["matched_terms"].append(term)

            is_better_match = result.get("similarity", 0) >= group["best_similarity"]
            if not group["best_block_id"] or (
                is_better_match and len(snippet or "") >= len(group["best_excerpt"])
            ):
                group["best_block_id"] = block_id
                group["best_excerpt"] = snippet or group["preview_content"] or ""

        documents = list(grouped.values())
        for item in documents:
            item["evidence_blocks"] = sorted(
                item["evidence_blocks"],
                key=lambda evidence: (
                    evidence.get("score", 0),
                    -evidence.get("block_index", 0),
                ),
                reverse=True,
            )
            if not item["best_block_id"] and item["evidence_blocks"]:
                item["best_block_id"] = item["evidence_blocks"][0]["block_id"]
            if not item["best_excerpt"]:
                item["best_excerpt"] = (
                    (item["evidence_blocks"][0].get("snippet") if item["evidence_blocks"] else "")
                    or item["preview_content"]
                )
            item["top_segments"] = sorted(
                item["top_segments"],
                key=lambda segment: segment.get("segment_index", 0),
            )[:3]
            item["results"] = sorted(
                item["results"],
                key=lambda result: result.get("similarity", 0),
                reverse=True,
            )

        documents.sort(
            key=lambda item: (
                item.get("score", 0),
                item.get("hit_count", 0),
                item.get("created_at_iso") or "",
            ),
            reverse=True,
        )
        return documents

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.fromisoformat(f"{normalized}T00:00:00")
            except ValueError:
                return None

    def _is_on_or_after(self, created_at_iso: Optional[str], lower_bound: str) -> bool:
        created_at = self._parse_datetime(created_at_iso)
        lower = self._parse_datetime(lower_bound)
        if created_at is None or lower is None:
            return False
        return created_at >= lower

    def _is_on_or_before(self, created_at_iso: Optional[str], upper_bound: str) -> bool:
        created_at = self._parse_datetime(created_at_iso)
        upper = self._parse_datetime(upper_bound)
        if created_at is None or upper is None:
            return False
        if len(upper_bound.strip()) == 10:
            upper = upper.replace(hour=23, minute=59, second=59, microsecond=999999)
        return created_at <= upper
