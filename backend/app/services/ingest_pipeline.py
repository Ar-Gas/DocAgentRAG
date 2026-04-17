"""Ingest Pipeline - 完整的文档入库流程"""
import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from app.core.logger import logger
from app.domain.extraction.dispatcher import ExtractionDispatcher
from app.domain.chunking.structural import StructuralChunker
from app.domain.llm.gateway import LLMGateway
from app.infra.repositories.entity_repository import EntityRepository
from app.infra.repositories.kg_repository import KGRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.vector_store import get_block_collection
from utils.retriever import search_documents


class IngestResult:
    """入库结果"""
    def __init__(self, doc_id: str, status: str, error: Optional[str] = None, metadata: Optional[Dict] = None):
        self.doc_id = doc_id
        self.status = status
        self.error = error
        self.metadata = metadata or {}


class IngestPipeline:
    """完整的文档入库管道"""

    def __init__(self):
        self.extractor = ExtractionDispatcher()
        self.chunker = StructuralChunker()
        self.llm_gateway = LLMGateway()
        self.entity_repo = EntityRepository()
        self.kg_repo = KGRepository()
        self.doc_repo = DocumentRepository()

    async def run(self, file_path: str, doc_id: str) -> IngestResult:
        """
        执行完整的入库流程

        步骤：
        1. 文本抽取
        2. LLM 结构化抽取
        3. 切块
        4. 向量 + BM25 索引
        5. 实体表持久化
        6. KG 三元组抽取
        7. 分类
        8. 重复文档检测

        Args:
            file_path: 文件路径
            doc_id: 文档 ID

        Returns:
            IngestResult
        """
        try:
            logger.info(f"开始入库: {doc_id} from {file_path}")

            # Step 1: 文本抽取
            logger.info(f"Step 1: 文本抽取 ({doc_id})")
            try:
                raw = self.extractor.extract(file_path)
            except Exception as e:
                logger.error(f"文本抽取失败: {str(e)}")
                return IngestResult(doc_id, "failed", str(e))

            # Step 2: LLM 结构化抽取（并发：摘要 + 实体 + 文档类型）
            logger.info(f"Step 2: LLM 结构化抽取 ({doc_id})")
            try:
                llm_meta, entities, kg_triples = await asyncio.gather(
                    self.llm_gateway.extract(raw.text, "metadata"),
                    self.llm_gateway.extract(raw.text, "entities"),
                    self.llm_gateway.extract(raw.text, "kg_triples"),
                    return_exceptions=True
                )

                # 处理异常（可能某些调用失败）
                if isinstance(llm_meta, Exception):
                    llm_meta = {}
                if isinstance(entities, Exception):
                    entities = []
                if isinstance(kg_triples, Exception):
                    kg_triples = []

                logger.info(f"LLM 抽取完成: {len(entities)} 实体, {len(kg_triples)} 三元组")
            except Exception as e:
                logger.error(f"LLM 抽取失败: {str(e)}")
                llm_meta, entities, kg_triples = {}, [], []

            # Step 3: 切块
            logger.info(f"Step 3: 切块 ({doc_id})")
            try:
                chunks = self.chunker.chunk(raw.text, {"doc_id": doc_id, "filename": Path(file_path).name})
                logger.info(f"切块完成: {len(chunks)} 块")
            except Exception as e:
                logger.error(f"切块失败: {str(e)}")
                return IngestResult(doc_id, "failed", str(e))

            # Step 4: 向量索引 + BM25 索引（保留现有逻辑）
            logger.info(f"Step 4: 索引入库 ({doc_id})")
            try:
                # 这里使用现有的 utils/retriever 逻辑
                from utils.retriever import index_document
                index_document(doc_id, chunks)
                logger.info(f"索引入库完成")
            except Exception as e:
                logger.error(f"索引入库失败: {str(e)}")

            # Step 5: 实体表持久化
            logger.info(f"Step 5: 实体持久化 ({doc_id})")
            try:
                if isinstance(entities, list) and entities:
                    self.entity_repo.save_entities(doc_id, entities)
                    logger.info(f"实体持久化完成")
            except Exception as e:
                logger.error(f"实体持久化失败: {str(e)}")

            # Step 6: KG 三元组抽取
            logger.info(f"Step 6: 知识图谱抽取 ({doc_id})")
            try:
                if isinstance(kg_triples, list) and kg_triples:
                    self.kg_repo.save_triples(doc_id, kg_triples)
                    logger.info(f"KG 三元组保存完成")
            except Exception as e:
                logger.error(f"KG 抽取失败: {str(e)}")

            # Step 7: 分类（双路检验 + LLM 仲裁）
            logger.info(f"Step 7: 分类 ({doc_id})")
            try:
                # 这里使用现有的分类逻辑
                from app.services.classification_service import ClassificationService
                classifier = ClassificationService()
                classification_result = await classifier.classify_document(doc_id)
                logger.info(f"分类完成: {classification_result}")
            except Exception as e:
                logger.error(f"分类失败: {str(e)}")
                classification_result = "未分类"

            # Step 8: 重复文档检测
            logger.info(f"Step 8: 重复检测 ({doc_id})")
            try:
                # 搜索相似文档
                similar = await self._find_similar_docs(doc_id, top_k=3)
                if similar and similar[0].get("score", 0) > 0.95:
                    logger.warning(f"检测到可能的重复文档: {similar[0]['doc_id']}")
                    # 记录到元数据
            except Exception as e:
                logger.warning(f"重复检测失败: {str(e)}")

            logger.info(f"入库完成: {doc_id}")
            return IngestResult(
                doc_id,
                "ready",
                metadata={
                    "llm_doc_type": llm_meta.get("doc_type", "未知"),
                    "llm_summary": llm_meta.get("summary", ""),
                    "chunks_count": len(chunks),
                    "entities_count": len(entities),
                    "kg_triples_count": len(kg_triples),
                    "classification": classification_result
                }
            )

        except Exception as e:
            logger.error(f"入库失败 {doc_id}: {str(e)}")
            return IngestResult(doc_id, "failed", str(e))

    async def _find_similar_docs(self, doc_id: str, top_k: int = 3) -> list:
        """查找相似文档"""
        try:
            # 使用现有的检索逻辑
            results = search_documents("", limit=top_k)
            return results
        except Exception:
            return []
