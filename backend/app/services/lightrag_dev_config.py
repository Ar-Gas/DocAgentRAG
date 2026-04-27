from __future__ import annotations

from pathlib import Path

_SEMANTIC_ARTIFACTS = (
    "vdb_entities.json",
    "vdb_relationships.json",
    "vdb_chunks.json",
    "kv_store_entity_chunks.json",
    "kv_store_relation_chunks.json",
    "kv_store_text_chunks.json",
)


def build_lightrag_env(
    *,
    root_dir: Path,
    doubao_api_key: str,
    doubao_llm_api_url: str,
    doubao_llm_model: str,
    embedding_host: str,
    embedding_model: str,
    embedding_dim: int = 1024,
) -> dict[str, str]:
    backend_dir = Path(root_dir) / "backend"
    working_dir = _resolve_working_dir(backend_dir, embedding_model, embedding_dim)
    return {
        "HOST": "127.0.0.1",
        "PORT": "9621",
        "WORKING_DIR": str(working_dir),
        "INPUT_DIR": str(backend_dir / "doc"),
        "LLM_BINDING": "openai",
        "EMBEDDING_BINDING": "openai",
        "LLM_BINDING_HOST": _openai_base_url_from_chat_endpoint(doubao_llm_api_url),
        "LLM_BINDING_API_KEY": doubao_api_key,
        "LLM_MODEL": doubao_llm_model,
        "EMBEDDING_BINDING_HOST": embedding_host.rstrip("/"),
        "EMBEDDING_BINDING_API_KEY": "local-bge-m3",
        "EMBEDDING_MODEL": embedding_model,
        "EMBEDDING_DIM": str(embedding_dim),
        "EMBEDDING_SEND_DIM": "false",
        "LLM_TIMEOUT": "300",
        "EMBEDDING_TIMEOUT": "120",
        "EMBEDDING_BATCH_NUM": "1",
        "EMBEDDING_FUNC_MAX_ASYNC": "1",
        "LARGE_DOC_THRESHOLD_CHUNKS": "80",
        "LARGE_DOC_CHUNK_SIZE": "2400",
        "LARGE_DOC_CHUNK_OVERLAP_SIZE": "150",
        "LARGE_DOC_CHUNK_MAX_ASYNC": "1",
        "MAX_PARALLEL_INSERT": "1",
        "MAX_ASYNC": "1",
        "TOP_K": "10",
        "CHUNK_TOP_K": "10",
        "SUMMARY_LANGUAGE": "Chinese",
        "LIGHTRAG_API_KEY": "",
    }


def render_lightrag_env(values: dict[str, str]) -> str:
    lines = [f"{key}={value}" for key, value in values.items()]
    return "\n".join(lines) + "\n"


def _openai_base_url_from_chat_endpoint(chat_endpoint: str) -> str:
    for marker in ("/chat/completions", "/responses"):
        if marker in chat_endpoint:
            return chat_endpoint.split(marker, 1)[0]
    return chat_endpoint.rstrip("/")


def _embedding_workspace_name(model_name: str, embedding_dim: int) -> str:
    safe_model = Path(str(model_name)).name or "embedding"
    safe_model = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in safe_model)
    return f"{safe_model}-{embedding_dim}d"


def _resolve_working_dir(backend_dir: Path, embedding_model: str, embedding_dim: int) -> Path:
    legacy_dir = backend_dir / "data" / "lightrag"
    model_dir = legacy_dir / _embedding_workspace_name(embedding_model, embedding_dim)
    if _should_use_legacy_workspace(legacy_dir, model_dir, embedding_model, embedding_dim):
        return legacy_dir
    return model_dir


def _should_use_legacy_workspace(
    legacy_dir: Path,
    model_dir: Path,
    embedding_model: str,
    embedding_dim: int,
) -> bool:
    normalized_model = Path(str(embedding_model)).name or str(embedding_model)
    if normalized_model != "bge-m3" or int(embedding_dim) != 1024:
        return False
    if _workspace_has_semantic_artifacts(model_dir):
        return False
    return _workspace_has_semantic_artifacts(legacy_dir)


def _workspace_has_semantic_artifacts(workspace_dir: Path) -> bool:
    return any(
        (workspace_dir / filename).is_file() and (workspace_dir / filename).stat().st_size > 0
        for filename in _SEMANTIC_ARTIFACTS
    )
