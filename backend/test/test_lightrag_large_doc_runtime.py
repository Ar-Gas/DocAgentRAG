import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import lightrag_runtime_patch as runtime_patch  # noqa: E402


def test_build_large_doc_profile_returns_profile_for_large_content(monkeypatch):
    monkeypatch.setenv("LARGE_DOC_THRESHOLD_CHUNKS", "80")
    monkeypatch.setenv("LARGE_DOC_CHUNK_SIZE", "2400")
    monkeypatch.setenv("LARGE_DOC_CHUNK_OVERLAP_SIZE", "150")
    monkeypatch.setenv("LARGE_DOC_CHUNK_MAX_ASYNC", "1")

    profile = runtime_patch.build_large_doc_profile(
        content_length=1200 * 80,
        default_chunk_token_size=1200,
    )

    assert profile == {
        "enabled": True,
        "estimated_chunks": 80,
        "chunk_token_size": 2400,
        "chunk_overlap_token_size": 150,
        "chunk_max_async": 1,
    }


def test_build_large_doc_profile_returns_none_for_small_content(monkeypatch):
    monkeypatch.setenv("LARGE_DOC_THRESHOLD_CHUNKS", "80")

    profile = runtime_patch.build_large_doc_profile(
        content_length=1200 * 10,
        default_chunk_token_size=1200,
    )

    assert profile is None


def test_merge_large_doc_profile_into_metadata_preserves_existing_fields(monkeypatch):
    monkeypatch.setenv("LARGE_DOC_THRESHOLD_CHUNKS", "80")
    monkeypatch.setenv("LARGE_DOC_CHUNK_SIZE", "2400")
    monkeypatch.setenv("LARGE_DOC_CHUNK_OVERLAP_SIZE", "150")
    monkeypatch.setenv("LARGE_DOC_CHUNK_MAX_ASYNC", "1")

    payload = runtime_patch.merge_large_doc_profile_into_metadata(
        metadata={"processing_start_time": 123, "keep": True},
        content_length=1200 * 100,
        default_chunk_token_size=1200,
    )

    assert payload["processing_start_time"] == 123
    assert payload["keep"] is True
    assert payload["large_doc_profile"]["enabled"] is True
    assert payload["large_doc_profile"]["estimated_chunks"] == 100


def test_wrap_chunking_func_uses_large_doc_profile_overrides(monkeypatch):
    calls = {}

    def fake_chunking(
        tokenizer,
        content,
        split_by_character,
        split_by_character_only,
        chunk_overlap_token_size,
        chunk_token_size,
    ):
        calls["chunk_overlap_token_size"] = chunk_overlap_token_size
        calls["chunk_token_size"] = chunk_token_size
        return [{"content": "x", "tokens": 1, "chunk_order_index": 0}]

    wrapped = runtime_patch.wrap_chunking_func(fake_chunking)
    tokenizer = object()
    content = "a" * 200

    result = wrapped(
        tokenizer,
        content,
        None,
        False,
        100,
        1200,
        chunk_profile={
            "enabled": True,
            "chunk_token_size": 2400,
            "chunk_overlap_token_size": 150,
            "chunk_max_async": 1,
        },
    )

    assert result[0]["content"] == "x"
    assert result[0]["tokens"] == 1
    assert result[0]["chunk_order_index"] == 0
    assert result[0]["large_doc_profile"]["chunk_token_size"] == 2400
    assert calls == {
        "chunk_overlap_token_size": 150,
        "chunk_token_size": 2400,
    }


def test_wrap_chunking_func_auto_detects_large_doc_and_injects_profile(monkeypatch):
    monkeypatch.setenv("LARGE_DOC_THRESHOLD_CHUNKS", "2")
    monkeypatch.setenv("LARGE_DOC_CHUNK_SIZE", "2400")
    monkeypatch.setenv("LARGE_DOC_CHUNK_OVERLAP_SIZE", "150")
    monkeypatch.setenv("LARGE_DOC_CHUNK_MAX_ASYNC", "1")

    calls = {}

    def fake_chunking(
        tokenizer,
        content,
        split_by_character,
        split_by_character_only,
        chunk_overlap_token_size,
        chunk_token_size,
    ):
        calls["chunk_overlap_token_size"] = chunk_overlap_token_size
        calls["chunk_token_size"] = chunk_token_size
        return [{"content": "x", "tokens": 1, "chunk_order_index": 0}]

    wrapped = runtime_patch.wrap_chunking_func(fake_chunking)
    result = wrapped(
        object(),
        "a" * 5000,
        None,
        False,
        100,
        1200,
    )

    assert calls == {
        "chunk_overlap_token_size": 150,
        "chunk_token_size": 2400,
    }
    assert result[0]["large_doc_profile"]["chunk_max_async"] == 1
    assert result[0]["large_doc_profile"]["chunk_token_size"] == 2400


def test_build_extract_entities_config_applies_local_override():
    global_config = {
        "llm_model_max_async": 2,
        "other": "value",
    }

    updated = runtime_patch.build_extract_entities_config(
        global_config,
        {
            "enabled": True,
            "chunk_max_async": 1,
        },
    )

    assert updated["llm_model_max_async"] == 1
    assert updated["other"] == "value"
    assert global_config["llm_model_max_async"] == 2


def test_enrich_metadata_with_large_doc_profile_adds_profile_for_new_doc(monkeypatch):
    monkeypatch.setenv("LARGE_DOC_THRESHOLD_CHUNKS", "2")
    monkeypatch.setenv("LARGE_DOC_CHUNK_SIZE", "2400")
    monkeypatch.setenv("LARGE_DOC_CHUNK_OVERLAP_SIZE", "150")
    monkeypatch.setenv("LARGE_DOC_CHUNK_MAX_ASYNC", "1")

    payload = runtime_patch.enrich_metadata_with_large_doc_profile(
        {
            "doc-1": {
                "content_length": 5000,
                "metadata": {},
            }
        },
        default_chunk_token_size=1200,
    )

    assert payload["doc-1"]["metadata"]["large_doc_profile"]["chunk_token_size"] == 2400


def test_build_chunk_profile_from_doc_uses_metadata_when_available():
    status_doc = SimpleNamespace(
        content_length=99999,
        metadata={
            "large_doc_profile": {
                "enabled": True,
                "estimated_chunks": 120,
                "chunk_token_size": 2400,
                "chunk_overlap_token_size": 150,
                "chunk_max_async": 1,
            }
        },
    )

    profile = runtime_patch.build_chunk_profile_from_doc(
        status_doc,
        default_chunk_token_size=1200,
    )

    assert profile["estimated_chunks"] == 120
    assert profile["chunk_token_size"] == 2400


def test_build_chunk_profile_from_doc_recomputes_when_metadata_missing(monkeypatch):
    monkeypatch.setenv("LARGE_DOC_THRESHOLD_CHUNKS", "80")
    monkeypatch.setenv("LARGE_DOC_CHUNK_SIZE", "2400")
    monkeypatch.setenv("LARGE_DOC_CHUNK_OVERLAP_SIZE", "150")
    monkeypatch.setenv("LARGE_DOC_CHUNK_MAX_ASYNC", "1")

    status_doc = SimpleNamespace(content_length=1200 * 90, metadata={})

    profile = runtime_patch.build_chunk_profile_from_doc(
        status_doc,
        default_chunk_token_size=1200,
    )

    assert profile["enabled"] is True
    assert profile["estimated_chunks"] == 90


def test_preserve_doc_status_metadata_merges_processing_fields():
    payload = {
        "doc-1": {
            "metadata": {"processing_start_time": 123},
            "status": "processing",
        }
    }
    existing = {
        "doc-1": {
            "metadata": {
                "large_doc_profile": {
                    "enabled": True,
                    "chunk_token_size": 2400,
                    "chunk_overlap_token_size": 150,
                    "chunk_max_async": 1,
                }
            }
        }
    }

    merged = runtime_patch.preserve_doc_status_metadata(payload, existing)

    assert merged["doc-1"]["metadata"]["processing_start_time"] == 123
    assert (
        merged["doc-1"]["metadata"]["large_doc_profile"]["chunk_token_size"] == 2400
    )


def test_patch_doc_status_upsert_preserves_large_doc_profile():
    saved_payloads = []

    class FakeDocStatus:
        async def get_by_id(self, doc_id):
            assert doc_id == "doc-1"
            return {
                "metadata": {
                    "large_doc_profile": {
                        "enabled": True,
                        "chunk_token_size": 2400,
                        "chunk_overlap_token_size": 150,
                        "chunk_max_async": 1,
                    }
                }
            }

        async def upsert(self, data):
            saved_payloads.append(data)

    doc_status = FakeDocStatus()
    runtime_patch.patch_doc_status_upsert(doc_status)

    asyncio.run(
        doc_status.upsert(
            {
                "doc-1": {
                    "status": "processing",
                    "metadata": {"processing_start_time": 123},
                }
            }
        )
    )

    assert saved_payloads[0]["doc-1"]["metadata"]["processing_start_time"] == 123
    assert (
        saved_payloads[0]["doc-1"]["metadata"]["large_doc_profile"]["chunk_token_size"]
        == 2400
    )


def test_patch_doc_status_upsert_enriches_new_doc_with_large_doc_profile(monkeypatch):
    monkeypatch.setenv("LARGE_DOC_THRESHOLD_CHUNKS", "2")
    monkeypatch.setenv("LARGE_DOC_CHUNK_SIZE", "2400")
    monkeypatch.setenv("LARGE_DOC_CHUNK_OVERLAP_SIZE", "150")
    monkeypatch.setenv("LARGE_DOC_CHUNK_MAX_ASYNC", "1")

    saved_payloads = []

    class FakeDocStatus:
        async def get_by_id(self, doc_id):
            assert doc_id == "doc-1"
            return None

        async def upsert(self, data):
            saved_payloads.append(data)

    doc_status = FakeDocStatus()
    runtime_patch.patch_doc_status_upsert(doc_status, default_chunk_token_size=1200)

    asyncio.run(
        doc_status.upsert(
            {
                "doc-1": {
                    "status": "pending",
                    "content_length": 5000,
                    "metadata": {},
                }
            }
        )
    )

    assert (
        saved_payloads[0]["doc-1"]["metadata"]["large_doc_profile"]["chunk_token_size"]
        == 2400
    )
