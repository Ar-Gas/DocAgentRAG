"""QA Service - 文档问答服务"""
import asyncio
import re
import unicodedata
from typing import List, Dict, Any, AsyncIterator, Optional

from app.core.logger import logger
from app.domain.llm.gateway import LLMGateway
from app.domain.llm.qa_chain import QAChain
from app.infra.repositories.qa_session_repository import QASessionRepository
from app.services.retrieval_service import RetrievalService


class QAService:
    """文档问答服务，支持 RAG + 流式输出 + 引用溯源"""

    QA_MAX_TOKENS = 512
    QA_TEMPERATURE = 0.2
    _DEFINITION_QUERY_PATTERNS = (
        r"^\s*什么是(?P<focus>.+?)\s*[?？]?\s*$",
        r"^\s*何为(?P<focus>.+?)\s*[?？]?\s*$",
        r"^\s*(?P<focus>.+?)是什么\s*[?？]?\s*$",
        r"^\s*(?P<focus>.+?)是指什么\s*[?？]?\s*$",
        r"^\s*(?P<focus>.+?)的定义是什么\s*[?？]?\s*$",
    )
    _DEFINITION_CUE_PATTERNS = (
        "是指",
        "主要指",
        "通常指",
        "可理解为",
        "可以理解为",
        "总称",
        "定义为",
        "称为",
    )

    def __init__(self):
        self.llm_gateway = LLMGateway()
        self.qa_chain = QAChain()
        self.qa_session_repo = QASessionRepository()
        self.retrieval_service = RetrievalService()

    @staticmethod
    def _result_document_id(result: Dict[str, Any]) -> str:
        return (
            result.get("document_id")
            or result.get("doc_id")
            or result.get("id")
            or ""
        )

    @staticmethod
    def _result_content(result: Dict[str, Any]) -> str:
        return (
            result.get("content")
            or result.get("content_snippet")
            or result.get("snippet")
            or result.get("text", "")
        )

    @staticmethod
    def _result_block_id(result: Dict[str, Any]) -> str:
        return str(result.get("block_id") or "").strip()

    @staticmethod
    def _result_score(result: Dict[str, Any]) -> float:
        try:
            return float(result.get("score", result.get("similarity", 0)) or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _result_filename(result: Dict[str, Any]) -> str:
        return str(result.get("filename") or "")

    @staticmethod
    def _result_page_number(result: Dict[str, Any]) -> Optional[int]:
        value = result.get("page_number")
        try:
            page_number = int(value)
        except (TypeError, ValueError):
            return None
        return page_number if page_number > 0 else None

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
        return re.sub(r"[\s\u3000]+", "", text)

    @classmethod
    def _clean_focus_text(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        cleaned = re.sub(r"[?？。．,，!！；;：:（）()\[\]【】\"“”'‘’]+$", "", cleaned)
        cleaned = re.sub(r"^(关于|请问)", "", cleaned)
        cleaned = re.sub(r"(的定义|的概念)$", "", cleaned)
        return cleaned.strip()

    @classmethod
    def _build_query_profile(cls, query: str) -> Dict[str, Any]:
        raw_query = str(query or "").strip()
        focus = ""
        for pattern in cls._DEFINITION_QUERY_PATTERNS:
            match = re.match(pattern, raw_query)
            if match:
                focus = cls._clean_focus_text(match.group("focus"))
                if focus:
                    break

        search_seed = focus or raw_query
        terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*|[\u4e00-\u9fff]{2,}", search_seed)
        search_terms = []
        for term in [focus, *terms, raw_query]:
            cleaned = cls._clean_focus_text(term)
            normalized = cls._normalize_text(cleaned)
            if normalized and normalized not in {cls._normalize_text(item) for item in search_terms}:
                search_terms.append(cleaned)

        return {
            "query": raw_query,
            "is_definition_query": bool(focus),
            "focus": focus,
            "search_terms": search_terms or ([raw_query] if raw_query else []),
            "block_query": focus or raw_query,
        }

    @classmethod
    def _term_coverage(cls, text: str, terms: List[str]) -> float:
        normalized_text = cls._normalize_text(text)
        normalized_terms = [
            cls._normalize_text(term)
            for term in terms
            if cls._normalize_text(term)
        ]
        if not normalized_text or not normalized_terms:
            return 0.0
        hits = sum(1 for term in normalized_terms if term in normalized_text)
        return hits / len(normalized_terms)

    @classmethod
    def _content_matches_focus(cls, content: str, focus_terms: List[str]) -> bool:
        normalized_content = cls._normalize_text(content)
        return any(
            cls._normalize_text(term) in normalized_content
            for term in focus_terms
            if cls._normalize_text(term)
        )

    @classmethod
    def _has_definition_cue(cls, content: str, focus: str) -> bool:
        if not content:
            return False
        for cue in cls._DEFINITION_CUE_PATTERNS:
            if focus and re.search(rf"{re.escape(focus)}[\u4e00-\u9fffA-Za-z0-9、，,]{0,10}{re.escape(cue)}", content):
                return True
            if cue in content:
                return True
        return False

    @classmethod
    def _rank_document_candidate(
        cls,
        candidate: Dict[str, Any],
        query_profile: Dict[str, Any],
    ) -> float:
        base_score = cls._result_score(candidate)
        filename = cls._result_filename(candidate)
        classification = str(candidate.get("classification_result") or "")
        preview_content = cls._result_content(candidate) or str(candidate.get("preview_content") or "")
        search_terms = query_profile.get("search_terms") or []
        focus = str(query_profile.get("focus") or "")
        is_definition_query = bool(query_profile.get("is_definition_query"))

        filename_coverage = cls._term_coverage(filename, search_terms)
        classification_coverage = cls._term_coverage(classification, search_terms)
        preview_coverage = cls._term_coverage(preview_content, search_terms)

        score = base_score
        score += filename_coverage * (0.55 if is_definition_query else 0.25)
        score += classification_coverage * (0.3 if is_definition_query else 0.12)
        score += preview_coverage * 0.12

        if focus:
            normalized_focus = cls._normalize_text(focus)
            if normalized_focus and normalized_focus in cls._normalize_text(filename):
                score += 0.4 if is_definition_query else 0.12
            if normalized_focus and normalized_focus in cls._normalize_text(classification):
                score += 0.22 if is_definition_query else 0.08
            if normalized_focus and normalized_focus in cls._normalize_text(preview_content):
                score += 0.08

        return round(score, 6)

    @classmethod
    def _rerank_document_candidates(
        cls,
        candidates: List[Dict[str, Any]],
        query_profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for candidate in candidates:
            document_id = cls._result_document_id(candidate)
            if not document_id:
                continue
            item = dict(candidate)
            item["_qa_rank_score"] = cls._rank_document_candidate(item, query_profile)
            enriched.append(item)
        enriched.sort(key=lambda item: item.get("_qa_rank_score", 0.0), reverse=True)
        return enriched

    @classmethod
    def _rank_block_result(
        cls,
        result: Dict[str, Any],
        query_profile: Dict[str, Any],
        document_scores: Dict[str, float],
        focus_match_available: bool,
    ) -> float:
        base_score = cls._result_score(result)
        document_id = cls._result_document_id(result)
        document_score = float(document_scores.get(document_id) or 0.0)
        content = cls._result_content(result)
        search_terms = query_profile.get("search_terms") or []
        focus = str(query_profile.get("focus") or "")
        is_definition_query = bool(query_profile.get("is_definition_query"))

        term_coverage = cls._term_coverage(content, search_terms)
        focus_match = cls._content_matches_focus(content, [focus] if focus else search_terms)

        score = base_score + document_score * (0.5 if is_definition_query else 0.25)
        score += term_coverage * (0.3 if is_definition_query else 0.15)

        if focus_match:
            score += 0.18 if is_definition_query else 0.08
        elif focus_match_available and is_definition_query:
            score -= 0.35

        if is_definition_query and focus and cls._has_definition_cue(content, focus):
            score += 0.08

        return round(score, 6)

    @classmethod
    def _rerank_block_results(
        cls,
        results: List[Dict[str, Any]],
        query_profile: Dict[str, Any],
        document_scores: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        focus_terms = [query_profile.get("focus")] if query_profile.get("focus") else list(query_profile.get("search_terms") or [])
        focus_match_available = any(
            cls._content_matches_focus(cls._result_content(result), focus_terms)
            for result in results
        )
        reranked = []
        for result in results:
            item = dict(result)
            item["_qa_rank_score"] = cls._rank_block_result(
                item,
                query_profile=query_profile,
                document_scores=document_scores,
                focus_match_available=focus_match_available,
            )
            reranked.append(item)
        reranked.sort(key=lambda item: item.get("_qa_rank_score", 0.0), reverse=True)
        return reranked

    @classmethod
    def _is_low_value_block(cls, result: Dict[str, Any]) -> bool:
        content = cls._result_content(result)
        normalized = re.sub(r"\s+", "", content or "").lower()
        if not normalized:
            return True

        if any(marker in normalized for marker in ("图书在版编目", "isbn")):
            return True
        if "cip" in normalized:
            return True

        chapter_markers = sum(
            content.count(marker)
            for marker in ("第一章", "第二章", "第三章", "第四章", "第五章", "第六章", "第七章", "第八章", "第九章", "第十章")
        )
        return "目录" in content and chapter_markers >= 2

    @classmethod
    def _ranking_score(
        cls,
        result: Dict[str, Any],
        document_scores: Optional[Dict[str, float]] = None,
    ) -> float:
        base_score = cls._result_score(result)
        document_id = cls._result_document_id(result)
        document_score = 0.0
        if document_scores and document_id:
            try:
                document_score = float(document_scores.get(document_id) or 0.0)
            except (TypeError, ValueError):
                document_score = 0.0
        return base_score + document_score * 0.25

    @classmethod
    def _dedupe_results(
        cls,
        results: List[Dict[str, Any]],
        document_scores: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for result in results:
            document_id = cls._result_document_id(result)
            block_id = cls._result_block_id(result)
            content = cls._result_content(result)
            key = (
                document_id,
                block_id or content[:200],
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(result)
        deduped.sort(
            key=lambda result: cls._ranking_score(result, document_scores=document_scores),
            reverse=True,
        )
        return deduped

    async def answer_stream(
        self,
        query: str,
        doc_ids: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        top_k: int = 8
    ) -> AsyncIterator[str]:
        """
        流式返回 RAG 问答结果

        Args:
            query: 用户问题
            doc_ids: 限定的文档 ID 列表（None = 全库问答）
            session_id: 会话 ID
            top_k: 检索 top-k 块

        Yields:
            答案片段（流式）
        """
        try:
            logger.info(f"QA Stream: {query}")
            normalized_doc_ids = [doc_id for doc_id in (doc_ids or []) if doc_id]

            # Step 1: 检索相关块
            logger.info("检索相关块...")
            blocks = await self._retrieve_blocks(query, normalized_doc_ids, top_k)

            if not blocks:
                answer = "未找到相关文档，无法回答。"
                if session_id:
                    self.qa_session_repo.save(
                        query=query,
                        doc_ids=normalized_doc_ids,
                        answer=answer,
                        citations=[],
                        session_id=session_id,
                    )
                yield answer
                return

            # Step 2: 构造 RAG context
            context = self.qa_chain.build_context(blocks)

            # Step 3: 构造 prompt
            prompt = self.qa_chain.build_prompt(query, context)

            # Step 4: 流式调用 LLM
            full_answer = ""
            logger.info("调用 LLM 生成答案...")
            async for chunk in self.llm_gateway.stream(
                prompt,
                task="qa",
                max_tokens=self.QA_MAX_TOKENS,
                temperature=self.QA_TEMPERATURE,
            ):
                full_answer += chunk
                yield chunk
                await asyncio.sleep(0.01)  # 模拟流式间隔

            # Step 5: 解析引用
            citations = self.qa_chain.parse_citations(full_answer)

            # Step 6: 存储会话
            if session_id:
                self.qa_session_repo.save(
                    query=query,
                    doc_ids=normalized_doc_ids or [b.get("doc_id", "") for b in blocks if b.get("doc_id")],
                    answer=full_answer,
                    citations=citations,
                    session_id=session_id,
                )

        except Exception as e:
            logger.error(f"QA 流式输出失败: {str(e)}")
            yield f"\n\n[错误] 问答失败: {str(e)}"

    async def answer(
        self,
        query: str,
        doc_ids: Optional[List[str]] = None,
        top_k: int = 8,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        同步问答接口

        Args:
            query: 用户问题
            doc_ids: 限定的文档 ID 列表
            top_k: 检索 top-k 块

        Returns:
            问答结果
        """
        try:
            normalized_doc_ids = [doc_id for doc_id in (doc_ids or []) if doc_id]

            # 检索相关块
            blocks = await self._retrieve_blocks(query, normalized_doc_ids, top_k)

            if not blocks:
                result = {
                    "query": query,
                    "answer": "未找到相关文档，无法回答。",
                    "citations": [],
                    "confidence": 0.0,
                }
                if session_id:
                    self.qa_session_repo.save(
                        query=query,
                        doc_ids=normalized_doc_ids,
                        answer=result["answer"],
                        citations=[],
                        session_id=session_id,
                    )
                    result["session_id"] = session_id
                return result

            # 构造 context 和 prompt
            context = self.qa_chain.build_context(blocks)
            prompt = self.qa_chain.build_prompt(query, context)

            # 调用 LLM
            response = await self.llm_gateway.call(
                prompt,
                task="qa",
                max_tokens=self.QA_MAX_TOKENS,
                temperature=self.QA_TEMPERATURE,
            )
            answer = response.content

            # 解析引用
            citations = self.qa_chain.parse_citations(answer)

            # 计算置信度（基于引用数量和 blocks 匹配度）
            confidence = min(1.0, len(citations) / 3.0 * 0.5 + 0.5)

            result = {
                "query": query,
                "answer": answer,
                "citations": citations,
                "confidence": confidence,
                "tokens_used": response.tokens_used,
            }
            if session_id:
                self.qa_session_repo.save(
                    query=query,
                    doc_ids=normalized_doc_ids or [b.get("doc_id", "") for b in blocks if b.get("doc_id")],
                    answer=answer,
                    citations=citations,
                    session_id=session_id,
                )
                result["session_id"] = session_id
            return result

        except Exception as e:
            logger.error(f"QA 问答失败: {str(e)}")
            return {
                "query": query,
                "answer": f"问答失败: {str(e)}",
                "citations": [],
                "confidence": 0.0,
                "error": str(e)
            }

    async def _retrieve_blocks(
        self,
        query: str,
        doc_ids: Optional[List[str]] = None,
        top_k: int = 8
    ) -> List[Dict[str, Any]]:
        """
        检索相关块

        Args:
            query: 查询
            doc_ids: 限定的文档 ID
            top_k: 返回块数

        Returns:
            相关块列表
        """
        try:
            normalized_doc_ids = [doc_id for doc_id in (doc_ids or []) if doc_id]
            narrowed_doc_ids = list(normalized_doc_ids)
            query_profile = self._build_query_profile(query)
            block_query = query_profile.get("block_query") or query

            document_search_result = await asyncio.to_thread(
                self.retrieval_service.workspace_search,
                query=query,
                mode="hybrid",
                retrieval_version="block",
                document_ids=normalized_doc_ids or None,
                limit=max(3, top_k),
                alpha=0.5,
                use_rerank=False,
                use_query_expansion=True,
                use_llm_rerank=False,
                group_by_document=True,
            )
            document_candidates = (
                document_search_result.get("documents")
                or document_search_result.get("results")
                or []
            )
            ranked_document_candidates = self._rerank_document_candidates(document_candidates, query_profile)
            candidate_doc_ids: List[str] = []
            candidate_doc_scores: Dict[str, float] = {}
            for candidate in ranked_document_candidates:
                document_id = self._result_document_id(candidate)
                if not document_id or document_id in candidate_doc_ids:
                    continue
                candidate_doc_ids.append(document_id)
                candidate_doc_scores[document_id] = float(candidate.get("_qa_rank_score") or self._result_score(candidate))
            if candidate_doc_ids:
                narrowed_doc_ids = candidate_doc_ids

            results: List[Dict[str, Any]] = []
            search_doc_ids = narrowed_doc_ids or normalized_doc_ids
            if search_doc_ids:
                scoped_doc_ids = search_doc_ids[:3]
                per_doc_limit = max(6 if query_profile.get("is_definition_query") else 5, top_k)
                for document_id in scoped_doc_ids:
                    search_result = await asyncio.to_thread(
                        self.retrieval_service.workspace_search,
                        query=block_query,
                        mode="hybrid",
                        retrieval_version="block",
                        document_ids=[document_id],
                        limit=per_doc_limit,
                        alpha=0.5,
                        use_rerank=False,
                        use_query_expansion=True,
                        use_llm_rerank=False,
                        group_by_document=False,
                    )
                    results.extend(search_result.get("results", []))
            else:
                search_result = await asyncio.to_thread(
                    self.retrieval_service.workspace_search,
                    query=block_query,
                    mode="hybrid",
                    retrieval_version="block",
                    document_ids=None,
                    limit=max(5, top_k),
                    alpha=0.5,
                    use_rerank=False,
                    use_query_expansion=True,
                    use_llm_rerank=False,
                    group_by_document=False,
                )
                results = search_result.get("results", [])

            if normalized_doc_ids:
                allowed_doc_ids = set(normalized_doc_ids)
                results = [r for r in results if self._result_document_id(r) in allowed_doc_ids]

            results = self._dedupe_results(results, document_scores=candidate_doc_scores)
            meaningful_results = [result for result in results if not self._is_low_value_block(result)]
            if meaningful_results:
                results = meaningful_results
            results = self._rerank_block_results(
                results,
                query_profile=query_profile,
                document_scores=candidate_doc_scores,
            )

            blocks = []
            for result in results[:top_k]:
                document_id = self._result_document_id(result)
                if not document_id:
                    continue
                block = {
                    "doc_id": document_id,
                    "filename": self._result_filename(result),
                    "content": self._result_content(result),
                    "section": result.get("section", ""),
                    "score": result.get("score", result.get("similarity", 0)),
                    "page_number": self._result_page_number(result),
                }
                blocks.append(block)

            return blocks

        except Exception as e:
            logger.warning(f"块检索失败: {str(e)}")
            return []
