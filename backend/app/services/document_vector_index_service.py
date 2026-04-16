import hashlib
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from app.infra.repositories.document_content_repository import DocumentContentRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from config import MAX_CHUNK_LENGTH, MIN_CHUNK_LENGTH
from utils.content_refiner import ContentRefiner
from utils.document_processor import process_document

logger = logging.getLogger(__name__)


def split_text_into_chunks(text, max_length=MAX_CHUNK_LENGTH, min_length=MIN_CHUNK_LENGTH):
    if not text:
        return []
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    sentence_pattern = re.compile(r"[^。！？!?；;\n]+(?:[。！？!?；;]|\n|$)")
    sentences = [item.strip() for item in sentence_pattern.findall(normalized) if item.strip()]
    if not sentences:
        sentences = [normalized]

    chunks = []
    current_chunk = ""

    def flush_current():
        nonlocal current_chunk
        chunk = current_chunk.strip()
        if len(chunk) >= min_length:
            chunks.append(chunk)
        current_chunk = ""

    for sentence in sentences:
        if len(sentence) > max_length:
            flush_current()
            for start in range(0, len(sentence), max_length):
                chunk = sentence[start:start + max_length].strip()
                if len(chunk) >= min_length:
                    chunks.append(chunk)
            continue

        if len(current_chunk) + len(sentence) <= max_length:
            current_chunk += sentence
        else:
            flush_current()
            current_chunk = sentence

    flush_current()
    return chunks


class DocumentVectorIndexService:
    def __init__(
        self,
        *,
        document_repository: Optional[DocumentRepository] = None,
        content_repository: Optional[DocumentContentRepository] = None,
        segment_repository: Optional[DocumentSegmentRepository] = None,
    ):
        self.document_repository = document_repository or DocumentRepository()
        self.content_repository = content_repository or DocumentContentRepository()
        self.segment_repository = segment_repository or DocumentSegmentRepository()

    def save_document_summary_for_classification(
        self,
        filepath,
        full_content: Optional[str] = None,
        parser_name: Optional[str] = None,
        display_filename: Optional[str] = None,
        *,
        classification_bridge_add: Optional[Callable[[dict], None]] = None,
    ):
        filepath_path = Path(filepath) if filepath else None
        if not filepath_path or not filepath_path.exists():
            logger.error("保存摘要失败：文件不存在 %s", filepath)
            return None, None
        try:
            document_id = str(uuid.uuid4())
            filename = display_filename or filepath_path.name
            ext = filepath_path.suffix.lower()
            content = full_content
            if content is None:
                success, content = process_document(filepath)
                if not success:
                    logger.error("文档内容无效：%s", filepath)
                    return None, None

            preview_content = content[:1000] if len(content) > 1000 else content
            mtime = filepath_path.stat().st_mtime
            doc_info = {
                "id": document_id,
                "filename": filename,
                "filepath": filepath,
                "file_type": ext,
                "preview_content": preview_content,
                "full_content_length": len(content),
                "parser_name": parser_name or ext.lstrip("."),
                "extraction_status": "ready",
                "created_at": mtime,
                "created_at_iso": datetime.fromtimestamp(mtime).isoformat(),
            }
            if self.document_repository.upsert(doc_info):
                self.content_repository.save(
                    document_id,
                    full_content=content,
                    preview_content=preview_content,
                    extraction_status="ready",
                    parser_name=parser_name or ext.lstrip("."),
                )
                if classification_bridge_add:
                    classification_bridge_add(doc_info)
                return document_id, doc_info
            return None, None
        except Exception as exc:
            logger.error("保存文档摘要失败: %s", exc)
            return None, None

    def save_document_to_chroma(
        self,
        filepath,
        document_id=None,
        use_refiner=True,
        save_chunk_info=True,
        full_content: Optional[str] = None,
        *,
        collection,
        update_document_info,
    ) -> bool:
        filepath_path = Path(filepath) if filepath else None
        if not filepath_path or not filepath_path.exists():
            logger.error("保存失败：文件不存在 %s", filepath)
            return False
        try:
            if not collection:
                return False

            document_id = document_id or str(uuid.uuid4())
            filename = filepath_path.name
            ext = filepath_path.suffix.lower()

            if full_content is None:
                success, full_content = process_document(filepath)
                if not success:
                    logger.error("文档内容无效：%s", filepath)
                    return False

            if use_refiner:
                try:
                    refiner = ContentRefiner()
                    chunks_data = refiner.refine_for_retrieval(full_content, document_id, chunk_size=MAX_CHUNK_LENGTH)
                    chunks = [chunk["content"] for chunk in chunks_data]
                    logger.info(
                        "使用提炼引擎优化内容: %s, 原始分片数%s -> 优化后%s",
                        filename,
                        len(split_text_into_chunks(full_content)),
                        len(chunks),
                    )
                except Exception as exc:
                    logger.warning("提炼引擎处理失败，使用传统分块: %s", exc)
                    chunks = split_text_into_chunks(full_content)
            else:
                chunks = split_text_into_chunks(full_content)

            if not chunks:
                logger.error("无有效分片：%s", filepath)
                return False

            self.content_repository.save(
                document_id,
                full_content=full_content,
                preview_content=full_content[:1000] if len(full_content) > 1000 else full_content,
                extraction_status="ready",
                parser_name=ext.lstrip("."),
            )
            if save_chunk_info:
                update_document_info(
                    document_id,
                    {
                        "chunk_info": {
                            "chunk_count": len(chunks),
                            "chunk_size": MAX_CHUNK_LENGTH,
                            "use_refiner": use_refiner,
                            "chunked_at": datetime.now().isoformat(),
                            "full_content_hash": hashlib.md5(full_content.encode("utf-8")).hexdigest(),
                        }
                    },
                )

            metadatas = []
            ids = []
            for index, chunk in enumerate(chunks):
                chunk_id = f"{document_id}_chunk_{index}"
                metadatas.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "filepath": filepath,
                        "file_type": ext,
                        "chunk_index": index,
                        "chunk_length": len(chunk),
                        "doc_internal_path": f"{filename}#chunk_{index}",
                        "refined": use_refiner,
                    }
                )
                ids.append(chunk_id)

            self.segment_repository.replace(
                document_id,
                [
                    {
                        "segment_id": ids[index],
                        "segment_index": index,
                        "segment_type": "chunk",
                        "content": chunk,
                        "metadata": metadatas[index],
                    }
                    for index, chunk in enumerate(chunks)
                ],
            )

            collection.add(documents=chunks, metadatas=metadatas, ids=ids)
            logger.info("文档保存成功：%s，共%s个分片", filename, len(chunks))
            return True
        except Exception as exc:
            logger.error("保存文档到Chroma失败: %s", exc)
            return False

    def re_chunk_document(
        self,
        document_id: str,
        *,
        use_refiner: bool,
        get_document_info,
        get_chroma_collection,
        save_document_to_chroma,
        update_document_info,
        fallback_roots: List[Path],
    ) -> bool:
        try:
            doc_info = get_document_info(document_id)
            if not doc_info:
                logger.error("重新分片失败：文档 %s 不存在", document_id)
                return False

            filename = doc_info.get("filename")
            filepath = doc_info.get("filepath")
            if not filepath or not Path(filepath).exists():
                logger.warning("原路径文件不存在，尝试查找文件：%s", filename)
                found_path = None
                for possible_dir in fallback_roots:
                    if possible_dir.exists():
                        for candidate in possible_dir.rglob(filename):
                            if candidate.is_file():
                                found_path = str(candidate)
                                break
                        if found_path:
                            break
                if found_path:
                    logger.info("找到文件：%s", found_path)
                    filepath = found_path
                    update_document_info(document_id, {"filepath": filepath})
                else:
                    logger.error("重新分片失败：无法找到文件 %s", filename)
                    return False

            collection = get_chroma_collection()
            if not collection:
                logger.error("重新分片失败：无法获取Chroma集合")
                return False
            try:
                results = collection.get(where={"document_id": document_id})
                if results and results.get("ids"):
                    collection.delete(ids=results["ids"])
                    logger.info("已删除旧分片：%s个", len(results["ids"]))
            except Exception as exc:
                logger.warning("删除旧分片时出错（可能不存在）: %s", exc)

            is_success = save_document_to_chroma(filepath, document_id=document_id, use_refiner=use_refiner)
            if is_success:
                logger.info("文档重新分片成功：%s", document_id)
            return is_success
        except Exception as exc:
            logger.error("重新分片失败: %s", exc, exc_info=True)
            return False

    def check_document_chunks(
        self,
        document_id: str,
        *,
        get_document_info,
        get_chroma_collection,
    ) -> dict:
        try:
            doc_info = get_document_info(document_id)
            if not doc_info:
                return {
                    "document_id": document_id,
                    "exists": False,
                    "has_chunks": False,
                    "chunk_count": 0,
                    "chunk_info": None,
                }

            collection = get_chroma_collection()
            chunk_count = 0
            if collection:
                try:
                    results = collection.get(where={"document_id": document_id})
                    chunk_count = len(results.get("ids", [])) if results else 0
                except Exception as exc:
                    logger.warning("检查Chroma分片数量失败: %s", exc)

            chunk_info = doc_info.get("chunk_info")
            return {
                "document_id": document_id,
                "exists": True,
                "has_chunks": chunk_count > 0,
                "chunk_count": chunk_count,
                "chunk_info": chunk_info,
                "in_sync": chunk_info and chunk_info.get("chunk_count") == chunk_count,
            }
        except Exception as exc:
            logger.error("检查文档分片状态失败: %s", exc)
            return {
                "document_id": document_id,
                "exists": False,
                "has_chunks": False,
                "chunk_count": 0,
                "chunk_info": None,
                "error": str(exc),
            }

    def list_document_chunk_embeddings(self, document_id: str, *, collection) -> List[dict]:
        if not document_id or collection is None:
            return []
        try:
            payload = collection.get(
                where={"document_id": document_id},
                include=["embeddings", "metadatas", "documents"],
            )
            results = []
            for embedding, metadata, content in zip(
                payload.get("embeddings") or [],
                payload.get("metadatas") or [],
                payload.get("documents") or [],
            ):
                if embedding is None:
                    continue
                results.append(
                    {
                        "embedding": list(embedding),
                        "metadata": metadata or {},
                        "content": content or "",
                    }
                )
            return results
        except Exception as exc:
            logger.error("获取文档分片向量失败: %s", exc)
            return []

    def retrieve_from_chroma(self, query, n_results=5, *, collection):
        if not query or n_results <= 0:
            logger.error("检索失败：查询为空或结果数非法")
            return []
        try:
            if not collection:
                return []
            return collection.query(query_texts=[query], n_results=n_results)
        except Exception as exc:
            logger.error("从Chroma检索失败: %s", exc)
            return []

    def delete_document(
        self,
        document_id: str,
        *,
        collection,
        delete_document_record,
        classification_bridge_delete,
    ) -> bool:
        if not document_id:
            logger.error("删除失败：文档ID为空")
            return False
        try:
            if collection:
                try:
                    results = collection.get(where={"document_id": document_id})
                    if results and results.get("ids"):
                        collection.delete(ids=results["ids"])
                except Exception:
                    pass
            classification_bridge_delete(document_id)
            delete_document_record(document_id)
            logger.info("文档%s删除成功", document_id)
            return True
        except Exception as exc:
            logger.error("删除文档失败: %s", exc)
            return False
