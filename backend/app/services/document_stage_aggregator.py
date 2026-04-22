from __future__ import annotations


def aggregate_runtime_view(stage_map: dict) -> dict:
    rag_stage = stage_map.get("rag_ingest", {})
    preview_stage = stage_map.get("local_preview_index", {})

    ingest_status = "queued"
    ingest_error = None
    if rag_stage.get("status") == "ready":
        ingest_status = "ready"
    elif rag_stage.get("status") in {"processing", "deferred"}:
        ingest_status = "processing"
    elif rag_stage.get("status") == "failed":
        ingest_status = "failed"
        ingest_error = rag_stage.get("error_message") or rag_stage.get("error_code")

    local_index_status = "queued"
    local_index_error = None
    if preview_stage.get("status") == "ready":
        local_index_status = "ready"
    elif preview_stage.get("status") == "failed":
        local_index_status = "failed"
        local_index_error = preview_stage.get("error_message")
    elif preview_stage.get("status") == "processing":
        local_index_status = "processing"

    return {
        "ingest_status": ingest_status,
        "ingest_error": ingest_error,
        "local_index_status": local_index_status,
        "local_index_error": local_index_error,
    }
