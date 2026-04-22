from app.services.rag_runtime_guard import RagCircuitBreaker, build_document_profile


def test_build_document_profile_marks_extra_large_pdf_for_deferred_rag():
    profile = build_document_profile(
        filename="操作系统导论.pdf",
        file_type=".pdf",
        content_length=605036,
        estimated_chunks=520,
    )

    assert profile["size_class"] == "xlarge"
    assert profile["defer_rag"] is True


def test_circuit_breaker_opens_after_repeated_failures():
    breaker = RagCircuitBreaker(failure_threshold=3)

    breaker.record_failure("embedding_unready")
    breaker.record_failure("embedding_unready")
    breaker.record_failure("embedding_unready")

    state = breaker.snapshot()

    assert state["open"] is True
    assert state["failure_count"] == 3
