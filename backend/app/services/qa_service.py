"""QA Service - 文档问答服务"""
import asyncio
from typing import List, Dict, Any, AsyncIterator, Optional

from app.core.logger import logger
from app.domain.llm.gateway import LLMGateway
from app.domain.llm.qa_chain import QAChain
from app.infra.repositories.qa_session_repository import QASessionRepository
from app.services.retrieval_service import RetrievalService


class QAService:
    """文档问答服务，支持 RAG + 流式输出 + 引用溯源"""

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
            async for chunk in self.llm_gateway.stream(prompt, task="qa"):
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
            response = await self.llm_gateway.call(prompt, task="qa", max_tokens=1000)
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
            # 使用改进的检索服务
            search_result = await self.retrieval_service.search_with_analysis(
                query,
                limit=top_k * 2,  # 多检索一些，后续会过滤
                use_rrf=True,
                use_llm_rerank=False  # QA 时先不用 rerank，防止多次 LLM 调用
            )

            results = search_result.get("results", [])

            # 过滤到指定的文档
            if doc_ids:
                results = [r for r in results if self._result_document_id(r) in doc_ids]

            # 转换为块格式
            blocks = []
            for result in results[:top_k]:
                document_id = self._result_document_id(result)
                if not document_id:
                    continue
                block = {
                    "doc_id": document_id,
                    "content": self._result_content(result),
                    "section": result.get("section", ""),
                    "score": result.get("score", result.get("similarity", 0)),
                }
                blocks.append(block)

            return blocks

        except Exception as e:
            logger.warning(f"块检索失败: {str(e)}")
            return []
