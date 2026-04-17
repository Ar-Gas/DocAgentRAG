from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.logger import get_logger, log_retrieval
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from app.infra.repositories.entity_repository import EntityRepository
from app.domain.retrieval.query_analyzer import QueryAnalyzer
from app.domain.retrieval.fusion import reciprocal_rank_fusion
from app.domain.retrieval.graph_retrieval import GraphRetrieval
from config import DOUBAO_API_KEY, DOUBAO_DEFAULT_LLM_MODEL
from app.services.errors import AppServiceError
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
from config import DATA_DIR
import asyncio


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def _segment_repository() -> DocumentSegmentRepository:
    return DocumentSegmentRepository(data_dir=DATA_DIR)


def get_all_documents():
    return _document_repository().list_all()


def list_document_segments(document_id: str):
    return _segment_repository().list(document_id)


def _result_document_id(result: Dict[str, Any]) -> str:
    return (
        result.get("document_id")
        or result.get("doc_id")
        or result.get("id")
        or ""
    )


class RetrievalService:
    def __init__(self):
        self.logger = get_logger(__name__)
        self.query_analyzer = QueryAnalyzer()
        self.graph_retrieval = GraphRetrieval()
        self.entity_repo = EntityRepository()

    async def search_with_analysis(
        self,
        query: str,
        limit: int = 20,
        use_rrf: bool = True,
        use_llm_rerank: bool = True,
        file_types: Optional[List[str]] = None
    ) -> Dict:
        """
        支持 LLM 分析的高级检索（三路检索 + RRF 融合）

        Args:
            query: 查询文本
            limit: 返回数量
            use_rrf: 是否使用 RRF 融合
            use_llm_rerank: 是否使用 LLM rerank
            file_types: 文件类型过滤

        Returns:
            包含分析信息和检索结果的字典
        """
        self._ensure_query(query)

        try:
            # Step 1: LLM Query 分析
            self.logger.info(f"Query 分析: {query}")
            analyzed_query = await self.query_analyzer.analyze(query)

            # Step 2: 三路并发检索
            vector_results = []
            bm25_results = []
            graph_results = []

            try:
                # 向量检索
                vector_results = search_documents(query, limit=limit, use_rerank=False, file_types=file_types)
            except Exception as e:
                self.logger.warning(f"向量检索失败: {str(e)}")

            try:
                # BM25 检索
                bm25_results = keyword_search(query, limit=limit, file_types=file_types)
            except Exception as e:
                self.logger.warning(f"BM25 检索失败: {str(e)}")

            try:
                # 图检索（基于实体）
                if analyzed_query.entity_filters:
                    for entity in analyzed_query.entity_filters[:3]:
                        entity_docs = await self.graph_retrieval.search_by_entity(entity, top_k=5)
                        graph_results.extend(entity_docs)
            except Exception as e:
                self.logger.warning(f"图检索失败: {str(e)}")

            # Step 3: RRF 融合
            if use_rrf and (vector_results or bm25_results or graph_results):
                fused_results = reciprocal_rank_fusion(
                    vector_results or [],
                    bm25_results or [],
                    graph_results or [],
                    weights={"vector": 0.4, "bm25": 0.4, "graph": 0.2}
                )
            else:
                fused_results = vector_results or bm25_results or graph_results or []

            # Step 4: LLM rerank
            if use_llm_rerank and fused_results:
                try:
                    from app.domain.llm.gateway import LLMGateway
                    llm_gateway = LLMGateway()
                    # 只对 top-20 进行 rerank
                    to_rerank = [
                        {
                            "id": _result_document_id(r),
                            "content": r.get("content") or r.get("text", "")[:200]
                        }
                        for r in fused_results[:20]
                        if _result_document_id(r)
                    ]
                    reranked = await llm_gateway.rerank(query, to_rerank, top_k=limit)
                    fused_results = reranked
                except Exception as e:
                    self.logger.warning(f"LLM rerank 失败: {str(e)}")

            return {
                "query": query,
                "total": len(fused_results),
                "results": fused_results,
                "query_analysis": {
                    "intent": analyzed_query.intent,
                    "expanded_queries": analyzed_query.expanded_queries,
                    "entity_filters": analyzed_query.entity_filters,
                    "time_filter": analyzed_query.time_filter,
                    "doc_type_hint": analyzed_query.doc_type_hint
                },
                "retrieval_method": "three-way RRF" if use_rrf else "vector/bm25"
            }

        except Exception as e:
            self.logger.error(f"高级检索失败: {str(e)}")
            # Fallback：使用原有的简单搜索
            return self.search(query, limit, use_rerank=False, file_types=file_types)

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
        self.logger.info("query_retrieval_stats")
        try:
            stats = get_document_stats() or {}
        except Exception as exc:
            self.logger.opt(exception=exc).error("query_retrieval_vector_stats_failed")
            stats = {}

        try:
            all_docs = list(get_all_documents() or [])
        except Exception as exc:
            self.logger.opt(exception=exc).error("query_retrieval_document_stats_failed")
            all_docs = []

        segment_document_ids = set()
        for doc in all_docs:
            if not isinstance(doc, dict):
                continue
            document_id = doc.get("id")
            if not document_id:
                continue
            try:
                if list_document_segments(document_id):
                    segment_document_ids.add(document_id)
            except Exception as exc:
                self.logger.opt(exception=exc).error(
                    "query_retrieval_segment_stats_failed document_id={}",
                    document_id,
                )

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
        return {
            "llm_available": is_llm_available(),
            "provider": "doubao" if DOUBAO_API_KEY else None,
            "doubao_configured": bool(DOUBAO_API_KEY),
            "default_model": DOUBAO_DEFAULT_LLM_MODEL,
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

    def regroup_workspace_payload(
        self,
        payload: Dict[str, Any],
        results: List[Dict[str, Any]],
        query: str = "",
    ) -> Dict[str, Any]:
        documents = self._group_workspace_results(results, query)
        return {
            **payload,
            "results": results,
            "documents": documents,
            "total_results": len(results),
            "total_documents": len(documents),
        }

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

        ready_document_ids = get_ready_block_document_ids(
            file_types=normalized_file_types,
            filename=filename,
            classification=classification,
            date_from=date_from,
            date_to=date_to,
        )
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
        documents = list(block_payload.get("documents") or [])[:normalized_limit]
        if group_by_document:
            results = self._flatten_surfaced_block_results(documents)
        else:
            results = self._normalize_block_results(
                list(block_payload.get("results") or [])[:normalized_limit],
                documents,
            )

        if not results:
            fallback_result = self._build_metadata_fallback_workspace_result(
                query=normalized_query,
                mode=normalized_mode,
                requested_retrieval_version=requested_retrieval_version,
                limit=normalized_limit,
                file_types=normalized_file_types,
                filename=filename,
                classification=classification,
                date_from=date_from,
                date_to=date_to,
                group_by_document=group_by_document,
                applied_filters=applied_filters,
                base_meta=block_payload.get("meta") or {},
                reason="missing_block_index" if not ready_document_ids else "block_search_empty",
            )
            if fallback_result is not None:
                return fallback_result

        if group_by_document and normalized_query and results:
            metadata_results = self._search_workspace_documents_by_metadata(
                documents=self._filter_workspace_documents(
                    file_types=normalized_file_types,
                    filename=filename,
                    classification=classification,
                    date_from=date_from,
                    date_to=date_to,
                ),
                query=normalized_query,
                limit=normalized_limit,
            )
            if metadata_results:
                combined_results = self._merge_workspace_results(results, metadata_results)
                documents = self._group_workspace_results(combined_results, normalized_query)[:normalized_limit]
                results = self._flatten_surfaced_block_results(documents)[:normalized_limit]
                block_meta = block_payload.get("meta") or {}
                block_payload["meta"] = {
                    **block_meta,
                    "metadata_blend_used": True,
                    "metadata_candidate_count": len(metadata_results),
                }

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
        # 3.2 仅缓存正常命中结果，避免把空结果/降级结果缓存住
        if result["total_results"] > 0 and not result["meta"].get("fallback_used"):
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
        _ = retrieval_version
        return "block"

    @staticmethod
    def _flatten_surfaced_block_results(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        flattened: List[Dict[str, Any]] = []
        for document in documents:
            document_id = document.get("document_id")
            document_base = {
                "document_id": document_id,
                "filename": document.get("filename", ""),
                "file_type": document.get("file_type", ""),
                "path": document.get("path", ""),
                "classification_result": document.get("classification_result"),
                "created_at_iso": document.get("created_at_iso"),
                "parser_name": document.get("parser_name"),
                "extraction_status": document.get("extraction_status"),
                "preview_content": document.get("preview_content", ""),
                "file_available": document.get("file_available", False),
            }
            for evidence in document.get("evidence_blocks") or []:
                snippet = evidence.get("snippet", "")
                score = evidence.get("score", 0.0)
                flattened.append(
                    {
                        **document_base,
                        "block_id": evidence.get("block_id"),
                        "block_index": evidence.get("block_index", 0),
                        "chunk_index": evidence.get("block_index", 0),
                        "block_type": evidence.get("block_type", "paragraph"),
                        "snippet": snippet,
                        "content_snippet": snippet,
                        "heading_path": evidence.get("heading_path", []),
                        "page_number": evidence.get("page_number"),
                        "score": score,
                        "similarity": score,
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

    @staticmethod
    def _normalize_block_results(
        results: List[Dict[str, Any]],
        documents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        document_lookup = {
            document.get("document_id"): document
            for document in documents
            if document.get("document_id")
        }
        normalized_results: List[Dict[str, Any]] = []
        for result in results:
            document = document_lookup.get(result.get("document_id"), {})
            snippet = result.get("content_snippet") or result.get("snippet", "")
            score = result.get("similarity", result.get("score", 0.0))
            normalized_results.append(
                {
                    "document_id": result.get("document_id"),
                    "filename": result.get("filename") or document.get("filename", ""),
                    "file_type": result.get("file_type") or document.get("file_type", ""),
                    "path": result.get("path") or document.get("path", ""),
                    "classification_result": result.get("classification_result", document.get("classification_result")),
                    "created_at_iso": result.get("created_at_iso", document.get("created_at_iso")),
                    "parser_name": result.get("parser_name", document.get("parser_name")),
                    "extraction_status": result.get("extraction_status", document.get("extraction_status")),
                    "preview_content": result.get("preview_content", document.get("preview_content", "")),
                    "file_available": result.get("file_available", document.get("file_available", False)),
                    "block_id": result.get("block_id"),
                    "block_index": result.get("block_index", 0),
                    "chunk_index": result.get("block_index", 0),
                    "block_type": result.get("block_type", "paragraph"),
                    "snippet": result.get("snippet", snippet),
                    "content_snippet": snippet,
                    "heading_path": result.get("heading_path", []),
                    "page_number": result.get("page_number"),
                    "score": score,
                    "similarity": score,
                    "match_reason": result.get("match_reason", ""),
                }
            )
        normalized_results.sort(
            key=lambda item: (
                item.get("score", 0.0),
                -item.get("block_index", 0),
            ),
            reverse=True,
        )
        return normalized_results

    @staticmethod
    def _merge_workspace_results(
        base_results: List[Dict[str, Any]],
        metadata_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged_results = [dict(item) for item in (base_results or [])]
        best_index_by_document: Dict[str, int] = {}
        best_score_by_document: Dict[str, float] = {}

        for index, item in enumerate(merged_results):
            document_id = item.get("document_id")
            if not document_id:
                continue
            score = item.get("similarity", item.get("score", 0.0)) or 0.0
            if document_id not in best_score_by_document or score >= best_score_by_document[document_id]:
                best_index_by_document[document_id] = index
                best_score_by_document[document_id] = score

        for item in metadata_results or []:
            document_id = item.get("document_id")
            if not document_id:
                continue
            item_score = item.get("similarity", item.get("score", 0.0)) or 0.0
            best_index = best_index_by_document.get(document_id)
            if best_index is None:
                merged_results.append(dict(item))
                best_index_by_document[document_id] = len(merged_results) - 1
                best_score_by_document[document_id] = item_score
                continue
            existing_best_score = best_score_by_document.get(document_id, 0.0)
            if existing_best_score >= 0.75 or item_score < existing_best_score:
                continue
            existing = dict(merged_results[best_index])
            merged_results[best_index] = {
                **existing,
                "block_id": item.get("block_id", existing.get("block_id")),
                "block_index": item.get("block_index", existing.get("block_index", 0)),
                "chunk_index": item.get("chunk_index", existing.get("chunk_index", existing.get("block_index", 0))),
                "block_type": item.get("block_type", existing.get("block_type", "paragraph")),
                "snippet": item.get("snippet", existing.get("snippet", "")),
                "content_snippet": item.get("content_snippet", existing.get("content_snippet", "")),
                "heading_path": item.get("heading_path", existing.get("heading_path", [])),
                "page_number": item.get("page_number", existing.get("page_number")),
                "score": item_score,
                "similarity": item_score,
                "match_reason": item.get("match_reason", existing.get("match_reason", "")),
            }
            best_score_by_document[document_id] = item_score

        merged_results.sort(
            key=lambda item: (
                item.get("similarity", item.get("score", 0.0)) or 0.0,
                item.get("created_at_iso") or "",
                -(item.get("block_index", item.get("chunk_index", 0)) or 0),
            ),
            reverse=True,
        )
        return merged_results

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

    def _build_metadata_fallback_workspace_result(
        self,
        *,
        query: str,
        mode: str,
        requested_retrieval_version: str,
        limit: int,
        file_types: Optional[List[str]],
        filename: Optional[str],
        classification: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
        group_by_document: bool,
        applied_filters: Dict[str, Any],
        base_meta: Dict[str, Any],
        reason: str,
    ) -> Optional[Dict[str, Any]]:
        candidate_documents = self._filter_workspace_documents(
            file_types=file_types,
            filename=filename,
            classification=classification,
            date_from=date_from,
            date_to=date_to,
        )
        fallback_results = self._search_workspace_documents_by_metadata(
            documents=candidate_documents,
            query=query,
            limit=limit,
        )
        if not fallback_results and candidate_documents:
            return {
                "query": query,
                "mode": mode,
                "retrieval_version_requested": requested_retrieval_version,
                "retrieval_version_used": "metadata_fallback",
                "total_results": 0,
                "total_documents": 0,
                "results": [],
                "documents": [],
                "meta": {
                    **base_meta,
                    "fallback_used": True,
                    "fallback_reason": reason,
                    "candidate_count": 0,
                    "expanded_queries": list(base_meta.get("expanded_queries") or ([query] if query else [])),
                },
                "applied_filters": applied_filters,
            }
        if not fallback_results:
            return None

        documents = self._group_workspace_results(fallback_results, query)[:limit]
        if group_by_document:
            results = self._flatten_surfaced_block_results(documents)[:limit]
        else:
            results = fallback_results[:limit]
        return {
            "query": query,
            "mode": mode,
            "retrieval_version_requested": requested_retrieval_version,
            "retrieval_version_used": "metadata_fallback",
            "total_results": len(results),
            "total_documents": len(documents),
            "results": results,
            "documents": documents,
            "meta": {
                **base_meta,
                "fallback_used": True,
                "fallback_reason": reason,
                "candidate_count": len(fallback_results),
                "expanded_queries": list(base_meta.get("expanded_queries") or ([query] if query else [])),
            },
            "applied_filters": applied_filters,
        }

    def _filter_workspace_documents(
        self,
        *,
        file_types: Optional[List[str]],
        filename: Optional[str],
        classification: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> List[Dict[str, Any]]:
        matched: List[Dict[str, Any]] = []
        for document in get_all_documents() or []:
            if not isinstance(document, dict):
                continue
            if not self._workspace_document_matches_filters(
                document,
                file_types=file_types,
                filename=filename,
                classification=classification,
                date_from=date_from,
                date_to=date_to,
            ):
                continue
            matched.append(document)
        return matched

    def _search_workspace_documents_by_metadata(
        self,
        *,
        documents: List[Dict[str, Any]],
        query: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        parser = get_query_parser()
        parsed = parser.parse(query) if query else None
        search_terms = self._collect_workspace_search_terms(parsed, query) if parsed else []
        scored_results: List[Dict[str, Any]] = []

        for document in documents:
            result = self._build_workspace_metadata_result(document, search_terms, query)
            if result is None:
                continue
            scored_results.append(result)

        if query:
            scored_results.sort(
                key=lambda item: (
                    item.get("similarity", 0.0),
                    item.get("created_at_iso") or "",
                ),
                reverse=True,
            )
        else:
            scored_results.sort(
                key=lambda item: item.get("created_at_iso") or "",
                reverse=True,
            )
        return scored_results[:limit]

    def _build_workspace_metadata_result(
        self,
        document: Dict[str, Any],
        search_terms: List[str],
        raw_query: str,
    ) -> Optional[Dict[str, Any]]:
        document_id = document.get("id")
        if not document_id:
            return None

        filename = str(document.get("filename", "") or "")
        classification = str(document.get("classification_result", "") or "")
        preview_content = str(document.get("preview_content", "") or "")

        if raw_query:
            filename_hits = self._count_workspace_term_hits(filename, search_terms)
            classification_hits = self._count_workspace_term_hits(classification, search_terms)
            preview_hits = self._count_workspace_term_hits(preview_content, search_terms)
            total_hits = filename_hits + classification_hits + preview_hits
            if total_hits <= 0:
                return None
            similarity = min(
                0.99,
                round(
                    filename_hits * 0.45
                    + classification_hits * 0.2
                    + preview_hits * 0.3
                    + min(total_hits, 6) * 0.03,
                    4,
                ),
            )
        else:
            similarity = 0.2

        snippet = self._extract_workspace_preview_snippet(
            preview_content,
            search_terms=search_terms,
            fallback_text=filename or classification,
        )
        match_reason = "preview match"
        if raw_query:
            lowered_terms = [term.lower() for term in search_terms if term]
            lowered_filename = filename.lower()
            lowered_classification = classification.lower()
            if any(term in lowered_filename for term in lowered_terms):
                match_reason = "filename match"
            elif any(term in lowered_classification for term in lowered_terms):
                match_reason = "classification match"

        return {
            "document_id": document_id,
            "filename": filename,
            "file_type": document.get("file_type", ""),
            "path": document.get("filepath") or document.get("path", ""),
            "classification_result": document.get("classification_result"),
            "created_at_iso": document.get("created_at_iso"),
            "parser_name": document.get("parser_name"),
            "extraction_status": document.get("extraction_status"),
            "preview_content": preview_content,
            "file_available": document.get("file_available", False),
            "block_id": f"{document_id}#preview",
            "block_index": 0,
            "chunk_index": 0,
            "block_type": "preview",
            "heading_path": [],
            "page_number": None,
            "similarity": similarity,
            "score": similarity,
            "snippet": snippet,
            "content_snippet": snippet,
            "match_reason": match_reason,
        }

    @staticmethod
    def _count_workspace_term_hits(text: str, search_terms: List[str]) -> int:
        lowered_text = (text or "").lower()
        hits = 0
        for term in search_terms:
            normalized = (term or "").strip().lower()
            if not normalized:
                continue
            hits += lowered_text.count(normalized)
        return hits

    @staticmethod
    def _extract_workspace_preview_snippet(
        preview_content: str,
        *,
        search_terms: List[str],
        fallback_text: str,
        radius: int = 90,
    ) -> str:
        text = (preview_content or "").strip()
        if not text:
            return (fallback_text or "").strip()[:240]

        lowered_text = text.lower()
        positions = []
        for term in search_terms:
            normalized = (term or "").strip().lower()
            if not normalized:
                continue
            position = lowered_text.find(normalized)
            if position >= 0:
                positions.append(position)
        if not positions:
            return text[:240]

        start = max(min(positions) - radius, 0)
        end = min(start + 240, len(text))
        return text[start:end]

    def _workspace_document_matches_filters(
        self,
        document: Dict[str, Any],
        *,
        file_types: Optional[List[str]],
        filename: Optional[str],
        classification: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> bool:
        normalized_file_types = self._normalize_file_types(file_types)
        if normalized_file_types:
            document_file_type = (document.get("file_type") or "").strip().lower().lstrip(".")
            document_family = self._workspace_file_type_family(document_file_type)
            if (
                document_file_type not in normalized_file_types
                and document_family not in normalized_file_types
            ):
                return False

        if filename and filename.strip().lower() not in str(document.get("filename", "")).lower():
            return False

        if classification:
            normalized_filter = classification.strip().lower()
            classification_id = str(document.get("classification_id") or "").strip().lower()
            classification_text = str(document.get("classification_result") or "未分类").lower()
            classification_path = str(document.get("classification_path") or "").lower()
            if (
                normalized_filter != classification_id
                and normalized_filter not in classification_text
                and normalized_filter not in classification_path
            ):
                return False

        created_at_iso = document.get("created_at_iso")
        if date_from and not self._workspace_datetime_is_on_or_after(created_at_iso, date_from):
            return False
        if date_to and not self._workspace_datetime_is_on_or_before(created_at_iso, date_to):
            return False
        return True

    @staticmethod
    def _workspace_file_type_family(file_type: str) -> str:
        family_map = {
            "pdf": "pdf",
            "doc": "word",
            "docx": "word",
            "word": "word",
            "ppt": "ppt",
            "pptx": "ppt",
            "presentation": "ppt",
            "xls": "excel",
            "xlsx": "excel",
            "csv": "excel",
            "excel": "excel",
            "txt": "text",
            "md": "text",
            "text": "text",
            "html": "web",
            "htm": "web",
            "web": "web",
            "eml": "email",
            "msg": "email",
            "email": "email",
        }
        normalized = (file_type or "").strip().lower().lstrip(".")
        return family_map.get(normalized, normalized)

    @staticmethod
    def _workspace_parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.fromisoformat(f"{normalized}T00:00:00")
            except ValueError:
                return None

    def _workspace_datetime_is_on_or_after(
        self,
        value: Optional[str],
        lower_bound: Optional[str],
    ) -> bool:
        created_at = self._workspace_parse_datetime(value)
        lower = self._workspace_parse_datetime(lower_bound)
        if created_at is None or lower is None:
            return False
        return created_at >= lower

    def _workspace_datetime_is_on_or_before(
        self,
        value: Optional[str],
        upper_bound: Optional[str],
    ) -> bool:
        created_at = self._workspace_parse_datetime(value)
        upper = self._workspace_parse_datetime(upper_bound)
        if created_at is None or upper is None:
            return False
        if len(str(upper_bound).strip()) == 10:
            upper = upper.replace(hour=23, minute=59, second=59, microsecond=999999)
        return created_at <= upper


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
                else result.get("block_index", result.get("chunk_index", 0))
            )
            block_id = (
                (current_segment or {}).get("segment_id")
                if current_segment
                else result.get("block_id") or f"{document_id}#{block_index}"
            )
            snippet = (
                result.get("content_snippet")
                or (current_segment or {}).get("content")
                or result.get("preview_content", "")
            )
            evidence = {
                "block_id": block_id,
                "block_index": block_index or 0,
                "block_type": result.get("block_type", "paragraph"),
                "snippet": snippet or "",
                "heading_path": result.get("heading_path", []),
                "score": result.get("similarity", 0),
                "page_number": (current_segment or {}).get("page_number"),
                "match_reason": result.get("match_reason", ""),
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
