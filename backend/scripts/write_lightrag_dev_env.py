from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.lightrag_dev_config import build_lightrag_env, render_lightrag_env
from config import (
    BASE_DIR,
    DOUBAO_API_KEY,
    DOUBAO_DEFAULT_LLM_MODEL,
    DOUBAO_LLM_API_URL,
    LOCAL_EMBEDDING_MODEL_NAME,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Write local LightRAG .env for DocAgentRAG development.")
    parser.add_argument(
        "--output",
        default=str(BASE_DIR / "lightrag.env"),
        help="Path to write the LightRAG .env file.",
    )
    parser.add_argument(
        "--embedding-host",
        default="http://127.0.0.1:8011/v1",
        help="OpenAI-compatible local embedding base URL.",
    )
    args = parser.parse_args()

    root_dir = BASE_DIR.parent
    env_values = build_lightrag_env(
        root_dir=root_dir,
        doubao_api_key=DOUBAO_API_KEY,
        doubao_llm_api_url=DOUBAO_LLM_API_URL,
        doubao_llm_model=DOUBAO_DEFAULT_LLM_MODEL,
        embedding_host=args.embedding_host,
        embedding_model=LOCAL_EMBEDDING_MODEL_NAME,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_lightrag_env(env_values), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
