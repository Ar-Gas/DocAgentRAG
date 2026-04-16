import base64
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.utils import embedding_functions

from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.runtime_artifact_repository import RuntimeArtifactRepository
from config import DATA_DIR, DOUBAO_API_KEY, DOUBAO_EMBEDDING_API_URL, DOUBAO_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_embed_consecutive_failures = 0
_EMBED_MAX_FAILURES = 3
_bge_ef = None
_EMBEDDING_DIM_ARTIFACT = "embedding_dimension"


def doubao_multimodal_embed(
    text: str,
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
) -> Optional[List[float]]:
    if not text and not image_url and not image_base64:
        logger.error("豆包嵌入失败：输入内容为空")
        return None

    try:
        input_data = []
        if text:
            input_data.append({"type": "text", "text": text})
        if image_url:
            input_data.append({"type": "image_url", "image_url": {"url": image_url}})
        elif image_base64:
            input_data.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}})

        response = requests.post(
            DOUBAO_EMBEDDING_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DOUBAO_API_KEY}",
            },
            json={"model": DOUBAO_EMBEDDING_MODEL, "input": input_data},
            timeout=30,
        )
        if response.status_code != 200:
            logger.error("豆包嵌入API调用失败: %s - %s", response.status_code, response.text)
            return None

        result = response.json()
        data = result.get("data")
        if isinstance(data, list) and data:
            embedding = data[0].get("embedding")
        elif isinstance(data, dict):
            embedding = data.get("embedding")
        else:
            logger.error("豆包嵌入响应格式错误: %s", result)
            return None
        if embedding:
            return embedding
        logger.error("豆包嵌入响应缺少embedding字段: %s", result)
        return None
    except requests.exceptions.Timeout:
        logger.error("豆包嵌入API超时")
        return None
    except requests.exceptions.RequestException as exc:
        logger.error("豆包嵌入API请求异常: %s", exc)
        return None
    except Exception as exc:
        logger.error("豆包嵌入处理异常: %s", exc, exc_info=True)
        return None


def doubao_batch_embed(texts: List[str]) -> List[Optional[List[float]]]:
    return [doubao_multimodal_embed(text) for text in texts]


def _get_bge_ef():
    global _bge_ef
    if _bge_ef is None:
        bge_model = os.getenv("BGE_MODEL", "BAAI/bge-small-zh-v1.5")
        logger.info("加载 BGE 本地模型: %s", bge_model)
        _bge_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=bge_model)
    return _bge_ef


def embed_text(text: str) -> Optional[List[float]]:
    global _embed_consecutive_failures

    if DOUBAO_API_KEY and _embed_consecutive_failures < _EMBED_MAX_FAILURES:
        emb = doubao_multimodal_embed(text)
        if emb is not None:
            _embed_consecutive_failures = 0
            return emb
        _embed_consecutive_failures += 1
        logger.warning(
            "Doubao embed 失败 (%s/%s)，%s",
            _embed_consecutive_failures,
            _EMBED_MAX_FAILURES,
            "切换至 BGE" if _embed_consecutive_failures >= _EMBED_MAX_FAILURES else "下次重试",
        )

    try:
        result = _get_bge_ef()([text])
        if result:
            return list(result[0])
    except Exception as exc:
        logger.error("BGE embed 失败: %s", exc)
    return None


def detect_and_lock_embedding_dim() -> None:
    try:
        test_emb = embed_text("维度检测")
        if test_emb is None:
            logger.warning("detect_and_lock_embedding_dim: embed_text 返回 None，跳过维度锁定")
            return
        current_dim = len(test_emb)
        artifacts = RuntimeArtifactRepository(data_dir=DATA_DIR)
        stored = artifacts.load(_EMBEDDING_DIM_ARTIFACT)
        if stored is None:
            artifacts.save(_EMBEDDING_DIM_ARTIFACT, {"dim": current_dim})
            logger.info("Embedding 维度已锁定: %s", current_dim)
        elif int(stored.get("dim", 0)) != current_dim:
            logger.warning(
                "⚠️  Embedding 维度不一致！已存储=%s，当前=%s。请运行 POST /api/v1/documents/batch/rechunk 修复。",
                stored.get("dim"),
                current_dim,
            )
        else:
            logger.info("Embedding 维度校验通过: %s", current_dim)
    except Exception as exc:
        logger.error("detect_and_lock_embedding_dim 失败: %s", exc)


class DoubaoEmbeddingFunction(EmbeddingFunction):
    def __init__(self, fallback_model_name: Optional[str] = None):
        self._fallback_model_name = fallback_model_name
        self._fallback_ef = None
        self._use_doubao = True
        self._doubao_fail_count = 0
        self._max_fail_count = 3
        logger.info("DoubaoEmbeddingFunction 初始化完成（延迟加载回退模型）")

    def _get_fallback_ef(self):
        if self._fallback_ef is None and self._fallback_model_name:
            logger.info("正在加载回退模型: %s", self._fallback_model_name)
            try:
                self._fallback_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=self._fallback_model_name
                )
                logger.info("回退模型加载成功")
            except Exception as exc:
                logger.error("回退模型加载失败: %s", exc)
        return self._fallback_ef

    def __call__(self, input: Documents) -> Embeddings:
        return self.embed_documents(input)

    def embed_documents(self, documents: Documents) -> Embeddings:
        if not documents:
            return []

        if self._use_doubao and self._doubao_fail_count < self._max_fail_count:
            embeddings = []
            for doc in documents:
                embedding = doubao_multimodal_embed(doc)
                if embedding is None:
                    self._doubao_fail_count += 1
                    if self._doubao_fail_count >= self._max_fail_count:
                        self._use_doubao = False
                    break
                embeddings.append(embedding)
            else:
                self._doubao_fail_count = 0
                return embeddings

        fallback_ef = self._get_fallback_ef()
        if fallback_ef:
            return fallback_ef(documents)
        raise RuntimeError("豆包嵌入不可用且未配置回退嵌入函数")

    def embed_query(self, query: str) -> List[float]:
        if self._use_doubao and self._doubao_fail_count < self._max_fail_count:
            embedding = doubao_multimodal_embed(query)
            if embedding is not None:
                self._doubao_fail_count = 0
                return embedding
            self._doubao_fail_count += 1
            if self._doubao_fail_count >= self._max_fail_count:
                self._use_doubao = False

        fallback_ef = self._get_fallback_ef()
        if fallback_ef and hasattr(fallback_ef, "embed_query"):
            return fallback_ef.embed_query(query)
        if fallback_ef:
            results = fallback_ef([query])
            return results[0] if results else []
        raise RuntimeError("嵌入函数不可用")


def generate_document_embedding(
    document_id: str,
    content: str,
    image_paths: Optional[List[str]] = None,
) -> Optional[List[float]]:
    if image_paths:
        for img_path in image_paths:
            try:
                with open(img_path, "rb") as handle:
                    img_base64 = base64.b64encode(handle.read()).decode("utf-8")
                embedding = doubao_multimodal_embed(content, image_base64=img_base64)
                if embedding:
                    logger.info("文档 %s 多模态嵌入生成成功", document_id)
                    return embedding
            except Exception as exc:
                logger.warning("处理图片 %s 失败: %s", img_path, exc)
    embedding = doubao_multimodal_embed(content)
    if embedding:
        logger.info("文档 %s 文本嵌入生成成功", document_id)
    return embedding


def generate_paragraph_embeddings(document_id: str, paragraphs: List[dict]) -> List[dict]:
    result = []
    for index, para in enumerate(paragraphs):
        content = para.get("content", "")
        if not content:
            continue
        result.append(
            {
                **para,
                "embedding": doubao_multimodal_embed(content),
                "embedding_model": DOUBAO_EMBEDDING_MODEL,
                "paragraph_index": index,
            }
        )
    logger.info("文档 %s 生成 %s 个段落嵌入", document_id, len(result))
    return result


def save_embeddings_to_document(
    document_id: str,
    doc_embedding: Optional[List[float]],
    paragraph_embeddings: Optional[List[dict]],
    *,
    document_repository: Optional[DocumentRepository] = None,
) -> bool:
    repository = document_repository or DocumentRepository(data_dir=DATA_DIR)
    doc_info = repository.get(document_id)
    if not doc_info:
        logger.error("保存嵌入失败：文档 %s 不存在", document_id)
        return False
    doc_info["embeddings"] = {
        "document_embedding": doc_embedding,
        "paragraph_embeddings": paragraph_embeddings,
        "embedding_model": DOUBAO_EMBEDDING_MODEL,
        "embedding_time": datetime.now().isoformat(),
    }
    return repository.upsert(doc_info)
