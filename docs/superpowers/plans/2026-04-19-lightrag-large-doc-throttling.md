# LightRAG Large-Doc Throttling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LightRAG automatically use a larger chunk profile for large documents and enforce dual-layer async throttling so long PDFs stop overwhelming the LLM extraction pipeline.

**Architecture:** Patch the LightRAG runtime in `site-packages` so per-document metadata stores a `large_doc_profile`, then reuse that metadata during chunking and entity extraction to select larger chunk sizes and a smaller per-document semaphore. Keep DocAgentRAG’s business API unchanged and only extend dev env defaults plus regression coverage around the patched runtime behavior.

**Tech Stack:** Python 3.12, FastAPI, pytest, LightRAG runtime in `backend/.venv/lib/python3.12/site-packages/lightrag`

---

## File Map

- Modify: `backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py`
  Purpose: compute large-doc profiles, persist them into `doc_status.metadata`, choose per-document chunk sizing, and pass local concurrency settings into extraction.
- Modify: `backend/.venv/lib/python3.12/site-packages/lightrag/operate.py`
  Purpose: enforce document-local semaphore control during chunk-level entity extraction while preserving the existing global LLM wrapper.
- Modify: `backend/app/services/lightrag_dev_config.py`
  Purpose: emit stable large-doc tuning defaults into `backend/lightrag.env`.
- Modify: `backend/test/test_lightrag_dev_config.py`
  Purpose: lock the generated dev env values for large-doc controls.
- Create: `backend/test/test_lightrag_large_doc_runtime.py`
  Purpose: regression coverage for large-doc profile selection and local semaphore throttling.

## Task 1: Lock Dev Config Defaults For Large-Doc Controls

**Files:**
- Modify: `backend/app/services/lightrag_dev_config.py`
- Modify: `backend/test/test_lightrag_dev_config.py`

- [ ] **Step 1: Write the failing test**

Add assertions to `backend/test/test_lightrag_dev_config.py`:

```python
    assert env["LARGE_DOC_THRESHOLD_CHUNKS"] == "80"
    assert env["LARGE_DOC_CHUNK_SIZE"] == "2400"
    assert env["LARGE_DOC_CHUNK_OVERLAP_SIZE"] == "150"
    assert env["LARGE_DOC_CHUNK_MAX_ASYNC"] == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_dev_config.py -q`

Expected: FAIL because the new large-doc env keys are not present yet.

- [ ] **Step 3: Write minimal implementation**

Update `backend/app/services/lightrag_dev_config.py` so `build_lightrag_env()` includes:

```python
        "LARGE_DOC_THRESHOLD_CHUNKS": "80",
        "LARGE_DOC_CHUNK_SIZE": "2400",
        "LARGE_DOC_CHUNK_OVERLAP_SIZE": "150",
        "LARGE_DOC_CHUNK_MAX_ASYNC": "1",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_dev_config.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/lightrag_dev_config.py backend/test/test_lightrag_dev_config.py
git commit -m "test: lock lightrag large-doc env defaults"
```

## Task 2: Add Failing Runtime Tests For Large-Doc Profile Selection

**Files:**
- Create: `backend/test/test_lightrag_large_doc_runtime.py`

- [ ] **Step 1: Write the failing test**

Create `backend/test/test_lightrag_large_doc_runtime.py` with these tests:

```python
import asyncio
import math
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lightrag import lightrag as lightrag_module  # noqa: E402


def test_build_large_doc_profile_returns_profile_for_large_content(monkeypatch):
    monkeypatch.setenv("LARGE_DOC_THRESHOLD_CHUNKS", "80")
    monkeypatch.setenv("LARGE_DOC_CHUNK_SIZE", "2400")
    monkeypatch.setenv("LARGE_DOC_CHUNK_OVERLAP_SIZE", "150")
    monkeypatch.setenv("LARGE_DOC_CHUNK_MAX_ASYNC", "1")

    profile = lightrag_module._build_large_doc_profile(
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
    profile = lightrag_module._build_large_doc_profile(
        content_length=1200 * 10,
        default_chunk_token_size=1200,
    )

    assert profile is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_large_doc_runtime.py -q`

Expected: FAIL with `AttributeError` because `_build_large_doc_profile` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add helper functions near the top of `backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py`:

```python
def _safe_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _build_large_doc_profile(
    content_length: int | None,
    default_chunk_token_size: int,
) -> dict[str, Any] | None:
    if not isinstance(content_length, int) or content_length <= 0:
        return None

    threshold_chunks = _safe_positive_int(
        os.getenv("LARGE_DOC_THRESHOLD_CHUNKS"), 80
    )
    estimated_chunks = math.ceil(content_length / max(default_chunk_token_size, 1))
    if estimated_chunks < threshold_chunks:
        return None

    return {
        "enabled": True,
        "estimated_chunks": estimated_chunks,
        "chunk_token_size": _safe_positive_int(
            os.getenv("LARGE_DOC_CHUNK_SIZE"), 2400
        ),
        "chunk_overlap_token_size": _safe_positive_int(
            os.getenv("LARGE_DOC_CHUNK_OVERLAP_SIZE"), 150
        ),
        "chunk_max_async": _safe_positive_int(
            os.getenv("LARGE_DOC_CHUNK_MAX_ASYNC"), 1
        ),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_large_doc_runtime.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py backend/test/test_lightrag_large_doc_runtime.py
git commit -m "test: cover lightrag large-doc profile selection"
```

## Task 3: Persist Large-Doc Profile Into Doc Status Metadata

**Files:**
- Modify: `backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py`
- Modify: `backend/test/test_lightrag_large_doc_runtime.py`

- [ ] **Step 1: Write the failing test**

Extend `backend/test/test_lightrag_large_doc_runtime.py` with:

```python
def test_prepare_doc_metadata_attaches_large_doc_profile(monkeypatch):
    monkeypatch.setenv("LARGE_DOC_THRESHOLD_CHUNKS", "80")
    monkeypatch.setenv("LARGE_DOC_CHUNK_SIZE", "2400")
    monkeypatch.setenv("LARGE_DOC_CHUNK_OVERLAP_SIZE", "150")
    monkeypatch.setenv("LARGE_DOC_CHUNK_MAX_ASYNC", "1")

    payload = lightrag_module._merge_large_doc_profile_into_metadata(
        metadata={},
        content_length=1200 * 100,
        default_chunk_token_size=1200,
    )

    assert payload["large_doc_profile"]["enabled"] is True
    assert payload["large_doc_profile"]["estimated_chunks"] == 100
    assert payload["large_doc_profile"]["chunk_token_size"] == 2400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_large_doc_runtime.py -q`

Expected: FAIL because `_merge_large_doc_profile_into_metadata` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add helper in `backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py`:

```python
def _merge_large_doc_profile_into_metadata(
    metadata: dict[str, Any] | None,
    content_length: int | None,
    default_chunk_token_size: int,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    profile = _build_large_doc_profile(content_length, default_chunk_token_size)
    if profile is None:
        merged.pop("large_doc_profile", None)
        return merged
    merged["large_doc_profile"] = profile
    return merged
```

Then update the `new_docs` dict creation in `apipeline_enqueue_documents()` so each inserted document stores:

```python
                "metadata": _merge_large_doc_profile_into_metadata(
                    metadata={},
                    content_length=len(content_data["content"]),
                    default_chunk_token_size=self.chunk_token_size,
                ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_large_doc_runtime.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py backend/test/test_lightrag_large_doc_runtime.py
git commit -m "feat: persist lightrag large-doc profile metadata"
```

## Task 4: Use Document-Specific Chunk Parameters During Processing

**Files:**
- Modify: `backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py`
- Modify: `backend/test/test_lightrag_large_doc_runtime.py`

- [ ] **Step 1: Write the failing test**

Extend `backend/test/test_lightrag_large_doc_runtime.py` with:

```python
def test_resolve_doc_chunking_profile_prefers_large_doc_metadata():
    status_doc = type(
        "StatusDoc",
        (),
        {
            "metadata": {
                "large_doc_profile": {
                    "enabled": True,
                    "chunk_token_size": 2400,
                    "chunk_overlap_token_size": 150,
                    "chunk_max_async": 1,
                }
            }
        },
    )()

    profile = lightrag_module._resolve_doc_processing_profile(
        status_doc=status_doc,
        default_chunk_token_size=1200,
        default_chunk_overlap_token_size=100,
        default_chunk_max_async=2,
    )

    assert profile == {
        "chunk_token_size": 2400,
        "chunk_overlap_token_size": 150,
        "chunk_max_async": 1,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_large_doc_runtime.py -q`

Expected: FAIL because `_resolve_doc_processing_profile` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add helper in `backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py`:

```python
def _resolve_doc_processing_profile(
    status_doc,
    default_chunk_token_size: int,
    default_chunk_overlap_token_size: int,
    default_chunk_max_async: int,
) -> dict[str, int]:
    metadata = getattr(status_doc, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    profile = metadata.get("large_doc_profile", {})
    if not isinstance(profile, dict) or not profile.get("enabled"):
        return {
            "chunk_token_size": default_chunk_token_size,
            "chunk_overlap_token_size": default_chunk_overlap_token_size,
            "chunk_max_async": default_chunk_max_async,
        }
    return {
        "chunk_token_size": _safe_positive_int(
            str(profile.get("chunk_token_size")), default_chunk_token_size
        ),
        "chunk_overlap_token_size": _safe_positive_int(
            str(profile.get("chunk_overlap_token_size")),
            default_chunk_overlap_token_size,
        ),
        "chunk_max_async": _safe_positive_int(
            str(profile.get("chunk_max_async")), default_chunk_max_async
        ),
    }
```

Then inside `process_document()` in `apipeline_process_enqueue_documents()`:

```python
                            doc_processing_profile = _resolve_doc_processing_profile(
                                status_doc=status_doc,
                                default_chunk_token_size=self.chunk_token_size,
                                default_chunk_overlap_token_size=self.chunk_overlap_token_size,
                                default_chunk_max_async=self.llm_model_max_async,
                            )
```

Use that profile for chunking:

```python
                                doc_processing_profile["chunk_overlap_token_size"],
                                doc_processing_profile["chunk_token_size"],
```

And pass the profile into `_process_extract_entities()`:

```python
                                self._process_extract_entities(
                                    chunks,
                                    pipeline_status,
                                    pipeline_status_lock,
                                    doc_processing_profile=doc_processing_profile,
                                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_large_doc_runtime.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py backend/test/test_lightrag_large_doc_runtime.py
git commit -m "feat: use lightrag per-document chunking profile"
```

## Task 5: Add Local Semaphore Control To Chunk Extraction

**Files:**
- Modify: `backend/.venv/lib/python3.12/site-packages/lightrag/operate.py`
- Modify: `backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py`
- Modify: `backend/test/test_lightrag_large_doc_runtime.py`

- [ ] **Step 1: Write the failing test**

Extend `backend/test/test_lightrag_large_doc_runtime.py` with:

```python
def test_resolve_chunk_max_async_uses_doc_processing_profile():
    value = lightrag_module._resolve_doc_processing_profile(
        status_doc=type(
            "StatusDoc",
            (),
            {"metadata": {"large_doc_profile": {"enabled": True, "chunk_max_async": 1}}},
        )(),
        default_chunk_token_size=1200,
        default_chunk_overlap_token_size=100,
        default_chunk_max_async=2,
    )

    assert value["chunk_max_async"] == 1
```

Add a second test that patches `operate.asyncio.Semaphore`:

```python
def test_extract_entities_uses_doc_local_chunk_max_async(monkeypatch):
    seen = {}

    class FakeSemaphore:
        def __init__(self, value):
            seen["value"] = value
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("lightrag.operate.asyncio.Semaphore", FakeSemaphore)
```

Then call a new helper that chooses the semaphore size and assert `seen["value"] == 1`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_large_doc_runtime.py -q`

Expected: FAIL because `extract_entities()` still hardcodes `global_config.get("llm_model_max_async", 4)`.

- [ ] **Step 3: Write minimal implementation**

In `backend/.venv/lib/python3.12/site-packages/lightrag/operate.py`, replace:

```python
    chunk_max_async = global_config.get("llm_model_max_async", 4)
```

with:

```python
    doc_processing_profile = global_config.get("doc_processing_profile", {}) or {}
    if not isinstance(doc_processing_profile, dict):
        doc_processing_profile = {}
    chunk_max_async = doc_processing_profile.get(
        "chunk_max_async",
        global_config.get("llm_model_max_async", 4),
    )
    if not isinstance(chunk_max_async, int) or chunk_max_async <= 0:
        chunk_max_async = global_config.get("llm_model_max_async", 4)
```

In `backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py`, change `_process_extract_entities()` to:

```python
    async def _process_extract_entities(
        self,
        chunk: dict[str, Any],
        pipeline_status=None,
        pipeline_status_lock=None,
        doc_processing_profile: dict[str, Any] | None = None,
    ) -> list:
        runtime_config = asdict(self)
        runtime_config["doc_processing_profile"] = dict(doc_processing_profile or {})
```

and pass `runtime_config` to `extract_entities()` instead of `asdict(self)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest test/test_lightrag_large_doc_runtime.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py backend/.venv/lib/python3.12/site-packages/lightrag/operate.py backend/test/test_lightrag_large_doc_runtime.py
git commit -m "feat: add lightrag local chunk extraction throttling"
```

## Task 6: Run Regression Coverage For Existing DocAgent Behavior

**Files:**
- Modify: `backend/test/test_lightrag_large_doc_runtime.py` if fixes are needed

- [ ] **Step 1: Run targeted existing tests**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest \
  test/test_lightrag_large_doc_runtime.py \
  test/test_lightrag_dev_config.py \
  test/test_lightrag_client.py \
  test/test_document_service_async_ingest.py -q
```

Expected: PASS

- [ ] **Step 2: Fix regressions minimally if any test fails**

If failures appear, constrain fixes to:

```python
# backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py
# backend/.venv/lib/python3.12/site-packages/lightrag/operate.py
# backend/app/services/lightrag_dev_config.py
```

Do not change DocAgent upload semantics.

- [ ] **Step 3: Re-run the same test suite**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest \
  test/test_lightrag_large_doc_runtime.py \
  test/test_lightrag_dev_config.py \
  test/test_lightrag_client.py \
  test/test_document_service_async_ingest.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py backend/.venv/lib/python3.12/site-packages/lightrag/operate.py backend/app/services/lightrag_dev_config.py backend/test/test_lightrag_large_doc_runtime.py backend/test/test_lightrag_dev_config.py
git commit -m "test: verify lightrag large-doc throttling regressions"
```

## Task 7: Runtime Verification With The Real Failed PDF

**Files:**
- Modify: `backend/lightrag.env` if regeneration is required

- [ ] **Step 1: Regenerate dev env**

Run: `cd backend && ./.venv/bin/python scripts/write_lightrag_dev_env.py`

Expected: `backend/lightrag.env` contains:

```env
LARGE_DOC_THRESHOLD_CHUNKS=80
LARGE_DOC_CHUNK_SIZE=2400
LARGE_DOC_CHUNK_OVERLAP_SIZE=150
LARGE_DOC_CHUNK_MAX_ASYNC=1
```

- [ ] **Step 2: Restart the LightRAG process so patched runtime and env are active**

Run the same startup method already in use for `9621`, ensuring it reads `backend/lightrag.env`.

Expected: `curl -s http://127.0.0.1:9621/health` returns healthy.

- [ ] **Step 3: Reprocess the failed document**

Run:

```bash
curl -s -X POST http://127.0.0.1:6008/api/v1/admin/lightrag/app/documents/reprocess_failed
```

Expected: `{"status":"reprocessing_started", ...}`

- [ ] **Step 4: Verify runtime behavior**

Run:

```bash
curl -s -X POST http://127.0.0.1:6008/api/v1/admin/lightrag/app/documents/paginated \
  -H 'Content-Type: application/json' \
  -d '{"page":1,"page_size":20}'
```

And:

```bash
tail -n 160 backend/lightrag.log
```

Expected:

- the target `重构：改善既有代码的设计（第2版）...pdf` no longer immediately fails with the old `Worker execution timeout after 360s`
- logs show the document entered processing with a large-doc profile or a smaller local chunk concurrency

- [ ] **Step 5: Commit runtime config changes if they are source-controlled**

```bash
git add backend/lightrag.env backend/app/services/lightrag_dev_config.py
git commit -m "chore: enable lightrag large-doc runtime defaults"
```
