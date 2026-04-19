from __future__ import annotations

import asyncio
import math
import os
from dataclasses import asdict, is_dataclass
from functools import wraps
from typing import Any, Callable

from lightrag.operate import extract_entities


def _safe_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def build_large_doc_profile(
    content_length: int | None,
    default_chunk_token_size: int,
) -> dict[str, Any] | None:
    if not isinstance(content_length, int) or content_length <= 0:
        return None

    safe_default_chunk_size = max(int(default_chunk_token_size or 0), 1)
    threshold_chunks = _safe_positive_int(
        os.getenv("LARGE_DOC_THRESHOLD_CHUNKS"), 80
    )
    estimated_chunks = math.ceil(content_length / safe_default_chunk_size)
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


def merge_large_doc_profile_into_metadata(
    metadata: dict[str, Any] | None,
    content_length: int | None,
    default_chunk_token_size: int,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    profile = build_large_doc_profile(content_length, default_chunk_token_size)
    if profile is None:
        merged.pop("large_doc_profile", None)
        return merged
    merged["large_doc_profile"] = profile
    return merged


def enrich_metadata_with_large_doc_profile(
    payload: dict[str, dict[str, Any]],
    *,
    default_chunk_token_size: int,
) -> dict[str, dict[str, Any]]:
    enriched: dict[str, dict[str, Any]] = {}
    for doc_id, doc_payload in (payload or {}).items():
        enriched[doc_id] = {
            **doc_payload,
            "metadata": merge_large_doc_profile_into_metadata(
                metadata=doc_payload.get("metadata"),
                content_length=doc_payload.get("content_length"),
                default_chunk_token_size=default_chunk_token_size,
            ),
        }
    return enriched


def wrap_chunking_func(chunking_func: Callable[..., Any]) -> Callable[..., Any]:
    def _wrapped(
        tokenizer,
        content,
        split_by_character=None,
        split_by_character_only=False,
        chunk_overlap_token_size=100,
        chunk_token_size=1200,
        *,
        chunk_profile: dict[str, Any] | None = None,
    ):
        resolved_chunk_profile = chunk_profile
        if resolved_chunk_profile is None:
            resolved_chunk_profile = build_large_doc_profile(
                len(content) if isinstance(content, str) else None,
                chunk_token_size,
            )

        effective_chunk_size = chunk_token_size
        effective_overlap_size = chunk_overlap_token_size

        if (
            isinstance(resolved_chunk_profile, dict)
            and resolved_chunk_profile.get("enabled")
        ):
            effective_chunk_size = int(
                resolved_chunk_profile.get("chunk_token_size") or chunk_token_size
            )
            effective_overlap_size = int(
                resolved_chunk_profile.get("chunk_overlap_token_size")
                or chunk_overlap_token_size
            )

        result = chunking_func(
            tokenizer,
            content,
            split_by_character,
            split_by_character_only,
            effective_overlap_size,
            effective_chunk_size,
        )
        if isinstance(result, list):
            return [
                {
                    **chunk_payload,
                    **(
                        {"large_doc_profile": dict(resolved_chunk_profile)}
                        if isinstance(resolved_chunk_profile, dict)
                        and resolved_chunk_profile.get("enabled")
                        else {}
                    ),
                }
                for chunk_payload in result
            ]
        return result

    return _wrapped


def build_extract_entities_config(
    global_config: dict[str, Any],
    chunk_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    updated = dict(global_config or {})
    if isinstance(chunk_profile, dict) and chunk_profile.get("enabled"):
        updated["llm_model_max_async"] = _safe_positive_int(
            str(chunk_profile.get("chunk_max_async")),
            int(updated.get("llm_model_max_async", 4) or 4),
        )
    return updated


def build_rag_global_config(rag: Any) -> dict[str, Any]:
    if is_dataclass(rag):
        config = asdict(rag)
    else:
        config = {
            key: value
            for key, value in vars(rag.__class__).items()
            if not key.startswith("_") and not callable(value)
        }
        config.update(
            {
                key: value
                for key, value in vars(rag).items()
                if not key.startswith("_") and not callable(value)
            }
        )
    return config


def normalize_large_doc_profile(
    profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(profile, dict) or not profile.get("enabled"):
        return None

    return {
        "enabled": True,
        "estimated_chunks": _safe_positive_int(
            str(profile.get("estimated_chunks")),
            0,
        ),
        "chunk_token_size": _safe_positive_int(
            str(profile.get("chunk_token_size")),
            2400,
        ),
        "chunk_overlap_token_size": _safe_positive_int(
            str(profile.get("chunk_overlap_token_size")),
            150,
        ),
        "chunk_max_async": _safe_positive_int(
            str(profile.get("chunk_max_async")),
            1,
        ),
    }


def inject_chunk_profile(
    chunks: dict[str, dict[str, Any]],
    chunk_profile: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    normalized = normalize_large_doc_profile(chunk_profile)
    if normalized is None:
        return chunks

    updated_chunks: dict[str, dict[str, Any]] = {}
    for chunk_id, chunk_payload in (chunks or {}).items():
        updated_chunks[chunk_id] = {
            **chunk_payload,
            "large_doc_profile": dict(normalized),
        }
    return updated_chunks


def build_chunk_profile_from_doc(
    status_doc: Any,
    default_chunk_token_size: int,
) -> dict[str, Any] | None:
    metadata = getattr(status_doc, "metadata", None)
    if isinstance(metadata, dict):
        normalized = normalize_large_doc_profile(metadata.get("large_doc_profile"))
        if normalized:
            return normalized

    return build_large_doc_profile(
        getattr(status_doc, "content_length", None),
        default_chunk_token_size,
    )


def preserve_doc_status_metadata(
    payload: dict[str, dict[str, Any]],
    existing_docs: dict[str, dict[str, Any] | None],
) -> dict[str, dict[str, Any]]:
    merged_payload: dict[str, dict[str, Any]] = {}

    for doc_id, doc_payload in (payload or {}).items():
        existing_doc = existing_docs.get(doc_id) or {}
        existing_metadata = existing_doc.get("metadata", {})
        new_metadata = dict(doc_payload.get("metadata") or {})

        if isinstance(existing_metadata, dict):
            large_doc_profile = existing_metadata.get("large_doc_profile")
            if large_doc_profile is not None and "large_doc_profile" not in new_metadata:
                new_metadata["large_doc_profile"] = large_doc_profile

        merged_payload[doc_id] = {
            **doc_payload,
            "metadata": new_metadata,
        }

    return merged_payload


def patch_doc_status_upsert(
    doc_status: Any,
    *,
    default_chunk_token_size: int = 1200,
) -> Any:
    if getattr(doc_status, "_docagent_large_doc_patch_applied", False):
        return doc_status

    original_upsert = doc_status.upsert
    original_get_by_id = doc_status.get_by_id

    async def _patched_upsert(data: dict[str, dict[str, Any]]) -> Any:
        existing_docs: dict[str, dict[str, Any] | None] = {}
        for doc_id in data.keys():
            existing_docs[doc_id] = await original_get_by_id(doc_id)
        enriched = enrich_metadata_with_large_doc_profile(
            data,
            default_chunk_token_size=default_chunk_token_size,
        )
        merged = preserve_doc_status_metadata(enriched, existing_docs)
        return await original_upsert(merged)

    doc_status.upsert = _patched_upsert
    doc_status._docagent_large_doc_patch_applied = True
    return doc_status


def _build_chunk_profile_from_chunks(
    chunk: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(chunk, dict) or not chunk:
        return None

    first_chunk = next(iter(chunk.values()), None)
    if not isinstance(first_chunk, dict):
        return None

    return normalize_large_doc_profile(first_chunk.get("large_doc_profile"))


def patch_process_extract_entities(rag: Any) -> Any:
    if getattr(rag, "_docagent_process_extract_patch_applied", False):
        return rag

    @wraps(rag._process_extract_entities)
    async def _patched_process_extract_entities(
        chunk: dict[str, Any], pipeline_status=None, pipeline_status_lock=None
    ):
        chunk_profile = _build_chunk_profile_from_chunks(chunk)
        global_config = build_extract_entities_config(
            build_rag_global_config(rag),
            chunk_profile,
        )

        chunk_max_async = global_config.get("llm_model_max_async", 4)
        semaphore = asyncio.Semaphore(max(int(chunk_max_async or 1), 1))

        async with semaphore:
            return await extract_entities(
                chunk,
                global_config=global_config,
                pipeline_status=pipeline_status,
                pipeline_status_lock=pipeline_status_lock,
                llm_response_cache=getattr(rag, "llm_response_cache", None),
                text_chunks_storage=getattr(rag, "text_chunks", None),
            )

    rag._process_extract_entities = _patched_process_extract_entities
    rag._docagent_process_extract_patch_applied = True
    return rag


def apply_light_rag_instance_patch(rag: Any) -> Any:
    if getattr(rag, "_docagent_large_doc_patch_applied", False):
        return rag

    rag.chunking_func = wrap_chunking_func(rag.chunking_func)
    patch_doc_status_upsert(
        rag.doc_status,
        default_chunk_token_size=getattr(rag, "chunk_token_size", 1200),
    )
    patch_process_extract_entities(rag)
    rag._docagent_large_doc_patch_applied = True
    return rag


def install_light_rag_runtime_patch(light_rag_cls: type[Any]) -> type[Any]:
    if getattr(light_rag_cls, "_docagent_runtime_patch_installed", False):
        return light_rag_cls

    original_init = light_rag_cls.__init__

    @wraps(original_init)
    def _patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        apply_light_rag_instance_patch(self)

    light_rag_cls.__init__ = _patched_init
    light_rag_cls._docagent_runtime_patch_installed = True
    return light_rag_cls


def apply_runtime_patch() -> type[Any]:
    from lightrag import LightRAG

    return install_light_rag_runtime_patch(LightRAG)
