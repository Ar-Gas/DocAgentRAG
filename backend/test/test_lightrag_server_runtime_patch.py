import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import lightrag_runtime_patch as runtime_patch  # noqa: E402


def test_apply_light_rag_instance_patch_wraps_chunking_and_doc_status():
    class FakeDocStatus:
        async def get_by_id(self, doc_id):
            return {"metadata": {}}

        async def upsert(self, data):
            return data

    class FakeRAG:
        def __init__(self):
            self.chunk_token_size = 1200
            self.chunk_overlap_token_size = 100
            self.chunking_func = lambda *args, **kwargs: []
            self.doc_status = FakeDocStatus()

        async def _process_extract_entities(
            self, chunk, pipeline_status=None, pipeline_status_lock=None
        ):
            return [chunk, pipeline_status, pipeline_status_lock]

    rag = FakeRAG()
    runtime_patch.apply_light_rag_instance_patch(rag)

    assert getattr(rag, "_docagent_large_doc_patch_applied", False) is True
    assert rag.chunking_func is not None
    assert asyncio.run(rag.doc_status.upsert({"doc-1": {"metadata": {}}})) == {
        "doc-1": {"metadata": {}}
    }


def test_apply_light_rag_instance_patch_uses_doc_profile_for_chunking(monkeypatch):
    class FakeDocStatus:
        async def get_by_id(self, doc_id):
            return {"metadata": {}}

        async def upsert(self, data):
            return data

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
        return [{"content": "chunk", "tokens": 1, "chunk_order_index": 0}]

    class FakeRAG:
        def __init__(self):
            self.chunk_token_size = 1200
            self.chunk_overlap_token_size = 100
            self.chunking_func = fake_chunking
            self.doc_status = FakeDocStatus()

        async def _process_extract_entities(
            self, chunk, pipeline_status=None, pipeline_status_lock=None
        ):
            return [chunk, pipeline_status, pipeline_status_lock]

    rag = FakeRAG()
    runtime_patch.apply_light_rag_instance_patch(rag)

    result = rag.chunking_func(
        object(),
        "abc",
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

    assert result[0]["content"] == "chunk"
    assert result[0]["tokens"] == 1
    assert result[0]["chunk_order_index"] == 0
    assert result[0]["large_doc_profile"]["chunk_token_size"] == 2400
    assert calls == {
        "chunk_overlap_token_size": 150,
        "chunk_token_size": 2400,
    }


def test_inject_chunk_profile_attaches_profile_to_each_chunk():
    chunks = {
        "chunk-1": {"content": "a"},
        "chunk-2": {"content": "b"},
    }

    updated = runtime_patch.inject_chunk_profile(
        chunks,
        {
            "enabled": True,
            "chunk_token_size": 2400,
            "chunk_overlap_token_size": 150,
            "chunk_max_async": 1,
        },
    )

    assert updated["chunk-1"]["large_doc_profile"]["chunk_token_size"] == 2400
    assert updated["chunk-2"]["large_doc_profile"]["chunk_max_async"] == 1


def test_patch_process_extract_entities_uses_chunk_profile_local_async(monkeypatch):
    calls = {}

    class FakeRAG:
        llm_model_max_async = 4
        llm_response_cache = object()
        text_chunks = object()

        def _docagent_asdict(self):
            return {"llm_model_max_async": self.llm_model_max_async}

        async def _process_extract_entities(self, *args, **kwargs):
            raise AssertionError("patched method should call extract_entities directly")

    async def fake_extract_entities(
        chunk,
        *,
        global_config,
        pipeline_status=None,
        pipeline_status_lock=None,
        llm_response_cache=None,
        text_chunks_storage=None,
    ):
        calls["chunk"] = chunk
        calls["local_async"] = global_config["llm_model_max_async"]
        calls["llm_response_cache"] = llm_response_cache
        calls["text_chunks_storage"] = text_chunks_storage
        return ["ok"]

    monkeypatch.setattr(runtime_patch, "extract_entities", fake_extract_entities)
    rag = FakeRAG()
    runtime_patch.patch_process_extract_entities(rag)

    result = asyncio.run(
        rag._process_extract_entities(
            {
                "chunk-1": {
                    "content": "a",
                    "large_doc_profile": {
                        "enabled": True,
                        "chunk_token_size": 2400,
                        "chunk_overlap_token_size": 150,
                        "chunk_max_async": 1,
                    },
                }
            }
        )
    )

    assert result == ["ok"]
    assert calls["local_async"] == 1
    assert calls["llm_response_cache"] is rag.llm_response_cache
    assert calls["text_chunks_storage"] is rag.text_chunks


def test_patch_process_extract_entities_preserves_full_global_config(monkeypatch):
    calls = {}

    class FakeRAG:
        llm_model_max_async = 4
        llm_model_func = object()
        entity_extract_max_gleaning = 1
        addon_params = {"language": "Chinese"}
        tokenizer = object()
        llm_response_cache = object()
        text_chunks = object()

        async def _process_extract_entities(self, *args, **kwargs):
            raise AssertionError("patched method should call extract_entities directly")

    async def fake_extract_entities(
        chunk,
        *,
        global_config,
        pipeline_status=None,
        pipeline_status_lock=None,
        llm_response_cache=None,
        text_chunks_storage=None,
    ):
        calls["global_config"] = global_config
        return ["ok"]

    monkeypatch.setattr(runtime_patch, "extract_entities", fake_extract_entities)
    rag = FakeRAG()
    runtime_patch.patch_process_extract_entities(rag)

    result = asyncio.run(
        rag._process_extract_entities(
            {
                "chunk-1": {
                    "content": "a",
                    "large_doc_profile": {
                        "enabled": True,
                        "chunk_token_size": 2400,
                        "chunk_overlap_token_size": 150,
                        "chunk_max_async": 1,
                    },
                }
            }
        )
    )

    assert result == ["ok"]
    assert calls["global_config"]["llm_model_max_async"] == 1
    assert calls["global_config"]["llm_model_func"] is rag.llm_model_func
    assert calls["global_config"]["entity_extract_max_gleaning"] == 1
    assert calls["global_config"]["addon_params"] == {"language": "Chinese"}
    assert calls["global_config"]["tokenizer"] is rag.tokenizer


def test_install_light_rag_runtime_patch_wraps_constructor(monkeypatch):
    calls = {"instance_patch": 0}

    class FakeLightRAG:
        def __init__(self, *args, **kwargs):
            self.chunk_token_size = 1200
            self.chunk_overlap_token_size = 100
            self.chunking_func = lambda *a, **k: []
            self.doc_status = type(
                "FakeDocStatus",
                (),
                {
                    "get_by_id": lambda self, doc_id: {"metadata": {}},
                    "upsert": lambda self, data: data,
                },
            )()

    def fake_apply_instance_patch(instance):
        calls["instance_patch"] += 1
        instance._patched = True
        return instance

    monkeypatch.setattr(runtime_patch, "apply_light_rag_instance_patch", fake_apply_instance_patch)

    patched_cls = runtime_patch.install_light_rag_runtime_patch(FakeLightRAG)
    instance = patched_cls()

    assert calls["instance_patch"] == 1
    assert instance._patched is True
