from app.services.document_stage_aggregator import aggregate_runtime_view


def test_aggregate_runtime_view_preserves_local_success_when_rag_failed():
    payload = aggregate_runtime_view(
        {
            "content_extract": {"status": "ready"},
            "local_preview_index": {"status": "ready"},
            "rag_ingest": {"status": "failed", "error_code": "embedding_unready"},
        }
    )

    assert payload["ingest_status"] == "failed"
    assert payload["local_index_status"] == "ready"
    assert payload["ingest_error"] == "embedding_unready"
