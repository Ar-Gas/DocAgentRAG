import shutil
import threading
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from chromadb import EphemeralClient, PersistentClient
from chromadb.utils import embedding_functions

from app.core.logger import logger
from app.infra.embedding_provider import get_local_embedding_model_name
from config import BGE_MODEL, CHROMA_DB_PATH

_chroma_client = None
_chroma_block_collection = None
_client_lock = threading.RLock()


def is_legacy_chroma_schema_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "collections.topic" in message or "no such column" in message and "collections" in message


def backup_legacy_chroma_store(reason: Exception, chroma_db_path: Path = CHROMA_DB_PATH) -> Optional[Path]:
    if not chroma_db_path.exists():
        chroma_db_path.mkdir(parents=True, exist_ok=True)
        return None

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = chroma_db_path.parent / f"{chroma_db_path.name}_legacy_{timestamp}"
    logger.warning("检测到旧版 Chroma 数据结构，备份到 {}，原因: {}", backup_path, reason)
    if backup_path.exists():
        shutil.rmtree(backup_path)
    chroma_db_path.rename(backup_path)
    chroma_db_path.mkdir(parents=True, exist_ok=True)
    return backup_path


def resolve_embedding_function():
    model_name = os.getenv("BGE_MODEL", BGE_MODEL)
    logger.info("加载本地嵌入模型: {}", model_name)
    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
    except Exception as exc:
        logger.error("BGE模型加载失败: {}", exc)
        logger.warning("回退到默认嵌入函数...")
        return embedding_functions.DefaultEmbeddingFunction()


def init_ephemeral_chroma_client() -> Tuple[object, object]:
    logger.warning("持久化 Chroma 不可用，回退到内存模式")
    client = EphemeralClient()
    embedding_function = resolve_embedding_function()
    block_collection = client.get_or_create_collection(name="document_blocks", embedding_function=embedding_function)
    return client, block_collection


def reset_clients() -> None:
    global _chroma_client, _chroma_block_collection
    with _client_lock:
        _chroma_client = None
        _chroma_block_collection = None


def init_chroma_client(
    *,
    chroma_db_path: Path = CHROMA_DB_PATH,
    recovered_legacy_schema: bool = False,
) -> Tuple[object, object]:
    global _chroma_client, _chroma_block_collection
    if _chroma_client is not None and _chroma_block_collection is not None:
        return _chroma_client, _chroma_block_collection

    with _client_lock:
        if _chroma_client is not None and _chroma_block_collection is not None:
            return _chroma_client, _chroma_block_collection

        client = PersistentClient(path=str(chroma_db_path))
        try:
            ef = resolve_embedding_function()
            block_collection = client.get_or_create_collection(name="document_blocks", embedding_function=ef)
            logger.info("Chroma block 客户端初始化成功（使用本地嵌入模型: {}）", get_local_embedding_model_name())
            _chroma_client = client
            _chroma_block_collection = block_collection
            return client, block_collection
        except Exception as chroma_error:
            if is_legacy_chroma_schema_error(chroma_error) and not recovered_legacy_schema:
                backup_legacy_chroma_store(chroma_error, chroma_db_path=chroma_db_path)
                return init_chroma_client(chroma_db_path=chroma_db_path, recovered_legacy_schema=True)
            logger.opt(exception=chroma_error).warning("持久化 Chroma 初始化失败")
            try:
                ef = embedding_functions.DefaultEmbeddingFunction()
                block_collection = client.get_or_create_collection(name="document_blocks", embedding_function=ef)
                logger.info("Chroma block 客户端初始化成功（使用默认嵌入函数）")
                _chroma_client = client
                _chroma_block_collection = block_collection
                return client, block_collection
            except Exception as fallback_error:
                if is_legacy_chroma_schema_error(fallback_error) and not recovered_legacy_schema:
                    backup_legacy_chroma_store(fallback_error, chroma_db_path=chroma_db_path)
                    return init_chroma_client(chroma_db_path=chroma_db_path, recovered_legacy_schema=True)
                logger.error("默认嵌入函数初始化失败: {}", fallback_error)
                try:
                    client, block_collection = init_ephemeral_chroma_client()
                    _chroma_client = client
                    _chroma_block_collection = block_collection
                    return client, block_collection
                except Exception as ephemeral_error:
                    logger.error("内存 Chroma 初始化失败: {}", ephemeral_error)
                    return None, None


def get_block_collection():
    global _chroma_block_collection
    if _chroma_block_collection is not None:
        return _chroma_block_collection

    _, block_collection = init_chroma_client()
    return block_collection
