from __future__ import annotations

from pathlib import Path


def build_lightrag_env(
    *,
    root_dir: Path,
    doubao_api_key: str,
    doubao_llm_api_url: str,
    doubao_llm_model: str,
    embedding_host: str,
    embedding_model: str,
) -> dict[str, str]:
    backend_dir = Path(root_dir) / "backend"
    return {
        "HOST": "127.0.0.1",
        "PORT": "9621",
        "WORKING_DIR": str(backend_dir / "data" / "lightrag"),
        "INPUT_DIR": str(backend_dir / "doc"),
        "LLM_BINDING": "openai",
        "EMBEDDING_BINDING": "openai",
        "LLM_BINDING_HOST": _openai_base_url_from_chat_endpoint(doubao_llm_api_url),
        "LLM_BINDING_API_KEY": doubao_api_key,
        "LLM_MODEL": doubao_llm_model,
        "EMBEDDING_BINDING_HOST": embedding_host.rstrip("/"),
        "EMBEDDING_BINDING_API_KEY": "local-bge-m3",
        "EMBEDDING_MODEL": embedding_model,
        "EMBEDDING_DIM": "1024",
        "EMBEDDING_SEND_DIM": "false",
        "EMBEDDING_TIMEOUT": "120",
        "EMBEDDING_BATCH_NUM": "2",
        "EMBEDDING_FUNC_MAX_ASYNC": "2",
        "MAX_PARALLEL_INSERT": "1",
        "MAX_ASYNC": "2",
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
