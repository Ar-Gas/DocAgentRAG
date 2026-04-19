from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.services.local_embedding_openai_service import create_embeddings_payload
from config import LOCAL_EMBEDDING_MODEL_NAME


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str | None = None
    encoding_format: str | None = "float"
    dimensions: int | None = None


app = FastAPI(title="DocAgentRAG Local BGE OpenAI-Compatible Embedding Server")


@app.get("/health")
def health_check():
    return {"status": "healthy", "model": LOCAL_EMBEDDING_MODEL_NAME}


@app.post("/v1/embeddings")
def create_embeddings(request: EmbeddingRequest):
    if request.dimensions not in (None, 1024):
        raise HTTPException(status_code=400, detail="bge-m3 local embedding dimension is fixed at 1024")
    try:
        return create_embeddings_payload(
            model=request.model or LOCAL_EMBEDDING_MODEL_NAME,
            input_value=request.input,
            encoding_format=request.encoding_format or "float",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("local_embedding_server:app", host="127.0.0.1", port=8011, reload=False)
