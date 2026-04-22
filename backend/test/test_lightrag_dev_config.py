import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.lightrag_dev_config import build_lightrag_env, render_lightrag_env  # noqa: E402


def test_build_lightrag_env_uses_local_embedding_endpoint_and_doubao_llm():
    env = build_lightrag_env(
        root_dir=Path("/workspace/DocAgentRAG"),
        doubao_api_key="secret-key",
        doubao_llm_api_url="https://ark.example.com/api/v3/chat/completions",
        doubao_llm_model="doubao-seed-2-0-mini-260215",
        embedding_host="http://127.0.0.1:8011/v1",
        embedding_model="bge-m3",
    )

    assert env["HOST"] == "127.0.0.1"
    assert env["PORT"] == "9621"
    assert env["WORKING_DIR"] == "/workspace/DocAgentRAG/backend/data/lightrag/bge-m3-1024d"
    assert env["INPUT_DIR"] == "/workspace/DocAgentRAG/backend/doc"
    assert env["LLM_BINDING"] == "openai"
    assert env["EMBEDDING_BINDING"] == "openai"
    assert env["LLM_BINDING_API_KEY"] == "secret-key"
    assert env["EMBEDDING_BINDING_API_KEY"] == "local-bge-m3"
    assert env["LLM_MODEL"] == "doubao-seed-2-0-mini-260215"
    assert env["EMBEDDING_MODEL"] == "bge-m3"
    assert env["EMBEDDING_BINDING_HOST"] == "http://127.0.0.1:8011/v1"
    assert env["EMBEDDING_DIM"] == "1024"
    assert env["WORKING_DIR"].endswith("backend/data/lightrag/bge-m3-1024d")
    assert env["LLM_TIMEOUT"] == "300"
    assert env["EMBEDDING_TIMEOUT"] == "120"
    assert env["EMBEDDING_BATCH_NUM"] == "1"
    assert env["EMBEDDING_FUNC_MAX_ASYNC"] == "1"
    assert env["LARGE_DOC_THRESHOLD_CHUNKS"] == "80"
    assert env["LARGE_DOC_CHUNK_SIZE"] == "2400"
    assert env["LARGE_DOC_CHUNK_OVERLAP_SIZE"] == "150"
    assert env["LARGE_DOC_CHUNK_MAX_ASYNC"] == "1"
    assert env["MAX_PARALLEL_INSERT"] == "1"
    assert env["MAX_ASYNC"] == "1"


def test_build_lightrag_env_uses_model_dimension_for_small_local_model():
    env = build_lightrag_env(
        root_dir=Path("/workspace/DocAgentRAG"),
        doubao_api_key="secret-key",
        doubao_llm_api_url="https://ark.example.com/api/v3/chat/completions",
        doubao_llm_model="doubao-seed-2-0-mini-260215",
        embedding_host="http://127.0.0.1:8011/v1",
        embedding_model="all-MiniLM-L6-v2",
        embedding_dim=384,
    )

    assert env["EMBEDDING_MODEL"] == "all-MiniLM-L6-v2"
    assert env["EMBEDDING_DIM"] == "384"
    assert env["WORKING_DIR"].endswith("backend/data/lightrag/all-MiniLM-L6-v2-384d")


def test_render_lightrag_env_writes_shell_friendly_lines():
    content = render_lightrag_env(
        {
            "HOST": "127.0.0.1",
            "PORT": "9621",
            "LLM_BINDING": "openai",
            "EMBEDDING_BINDING": "openai",
        }
    )

    assert "HOST=127.0.0.1" in content
    assert "PORT=9621" in content
    assert "LLM_BINDING=openai" in content
    assert content.endswith("\n")


def test_build_lightrag_env_trims_responses_endpoint_to_openai_base_url():
    env = build_lightrag_env(
        root_dir=Path("/workspace/DocAgentRAG"),
        doubao_api_key="secret-key",
        doubao_llm_api_url="https://ark.example.com/api/v3/responses",
        doubao_llm_model="doubao-seed-2-0-mini-260215",
        embedding_host="http://127.0.0.1:8011/v1",
        embedding_model="bge-m3",
    )

    assert env["LLM_BINDING_HOST"] == "https://ark.example.com/api/v3"
