from __future__ import annotations

import os
import threading

from fastapi import Depends
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.infra.embedding_provider import get_bge_model_status, warmup_bge_model
from app.services.local_embedding_openai_service import create_embeddings_payload
from config import LOCAL_EMBEDDING_DIM, LOCAL_EMBEDDING_MODEL_NAME


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str | None = None
    encoding_format: str | None = "float"
    dimensions: int | None = None


app = FastAPI(title="DocAgentRAG Local BGE OpenAI-Compatible Embedding Server")


@app.get("/health")
def health_check(model_status: dict = Depends(get_bge_model_status)):
    state = str(model_status.get("state") or "unloaded").lower()
    if state == "ready":
        return {
            "status": "healthy",
            "model": model_status.get("model") or LOCAL_EMBEDDING_MODEL_NAME,
            "liveness": "up",
            "readiness": "ready",
            "ready": True,
            "loaded_at": model_status.get("loaded_at"),
        }
    if state == "failed":
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "model": model_status.get("model") or LOCAL_EMBEDDING_MODEL_NAME,
                "liveness": "up",
                "readiness": "failed",
                "ready": False,
                "detail": model_status.get("detail") or "BGE model load failed",
            },
        )
    return {
        "status": "warming_up",
        "model": model_status.get("model") or LOCAL_EMBEDDING_MODEL_NAME,
        "liveness": "up",
        "readiness": "warming_up",
        "ready": False,
    }


@app.post("/v1/embeddings")
def create_embeddings(request: EmbeddingRequest):
    if request.dimensions not in (None, LOCAL_EMBEDDING_DIM):
        raise HTTPException(
            status_code=400,
            detail=f"{LOCAL_EMBEDDING_MODEL_NAME} local embedding dimension is fixed at {LOCAL_EMBEDDING_DIM}",
        )
    try:
        return create_embeddings_payload(
            model=request.model or LOCAL_EMBEDDING_MODEL_NAME,
            input_value=request.input,
            encoding_format=request.encoding_format or "float",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"BGE model load failed or unavailable: {exc}") from exc


def _prewarm_enabled() -> bool:
    return os.getenv("LOCAL_EMBEDDING_PREWARM", "true").strip().lower() not in {"0", "false", "no"}


def start_background_warmup() -> None:
    if not _prewarm_enabled():
        return
    thread = threading.Thread(target=warmup_bge_model, name="bge-model-warmup", daemon=True)
    thread.start()


if __name__ == "__main__":
    import uvicorn

    start_background_warmup()
    uvicorn.run("local_embedding_server:app", host="127.0.0.1", port=8011, reload=False)
