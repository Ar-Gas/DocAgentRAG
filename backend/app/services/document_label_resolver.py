import os
from typing import Dict, List

from app.domain.classification_contract import (
    SPECIAL_ERROR_LABEL,
    first_usable_text,
    is_unusable_classification_text,
    normalize_classification_label,
)
from app.domain.llm.gateway import LLMGateway
from app.infra.repositories.document_content_repository import DocumentContentRepository
from config import DATA_DIR


def _document_content_repository() -> DocumentContentRepository:
    return DocumentContentRepository(data_dir=DATA_DIR)


def get_document_content_record(document_id: str):
    return _document_content_repository().get(document_id)


def source_text_candidates(
    document_id: str,
    doc_info: Dict,
    source_text_candidates_override: List[str] | None = None,
) -> List[str]:
    content_record = get_document_content_record(document_id) or {}
    return [
        *(source_text_candidates_override or []),
        doc_info.get("preview_content") or "",
        content_record.get("preview_content") or "",
        content_record.get("full_content") or "",
        doc_info.get("full_content") or "",
        doc_info.get("content") or "",
        doc_info.get("excerpt") or "",
        doc_info.get("summary_source") or "",
    ]


def load_source_text(
    document_id: str,
    doc_info: Dict,
    source_text_candidates_override: List[str] | None = None,
) -> str:
    return first_usable_text(
        source_text_candidates(document_id, doc_info, source_text_candidates_override)
    )


def is_error_document(
    document_id: str,
    doc_info: Dict,
    source_text_candidates_override: List[str] | None = None,
) -> bool:
    source_text = load_source_text(document_id, doc_info, source_text_candidates_override)
    if source_text:
        return False
    return any(
        is_unusable_classification_text(text)
        for text in source_text_candidates(document_id, doc_info, source_text_candidates_override)
        if str(text or "").strip()
    )


async def resolve_document_label(
    document_id: str,
    doc_info: Dict,
    llm_gateway: LLMGateway | None = None,
    source_text_candidates_override: List[str] | None = None,
) -> Dict:
    source_text = load_source_text(document_id, doc_info, source_text_candidates_override)
    if is_error_document(document_id, doc_info, source_text_candidates_override):
        return {
            "label": SPECIAL_ERROR_LABEL,
            "source_text": "",
            "is_error": True,
            "source": "error_text",
        }

    gateway = llm_gateway or LLMGateway()
    try:
        label = normalize_classification_label(
            await gateway.classify(
                title=doc_info.get("filename", ""),
                text=source_text[:500],
            )
        )
    except Exception:
        label = None
    if label:
        return {
            "label": label,
            "source_text": source_text,
            "is_error": False,
            "source": "llm",
        }

    for candidate in _filename_heuristic_candidates(doc_info.get("filename", "")):
        fallback = normalize_classification_label(candidate)
        if fallback:
            if fallback == SPECIAL_ERROR_LABEL:
                return {
                    "label": SPECIAL_ERROR_LABEL,
                    "source_text": source_text,
                    "is_error": True,
                    "source": "heuristic",
                }
            return {
                "label": fallback,
                "source_text": source_text,
                "is_error": False,
                "source": "heuristic",
            }

    return {
        "label": SPECIAL_ERROR_LABEL,
        "source_text": source_text,
        "is_error": True,
        "source": "heuristic",
    }


def _filename_heuristic_candidates(filename: str) -> List[str]:
    normalized = str(filename or "").strip()
    if not normalized:
        return []

    basename = os.path.basename(normalized)
    stem, _ = os.path.splitext(basename)
    candidates = [stem, basename, normalized]

    unique: List[str] = []
    for item in candidates:
        value = str(item or "").strip()
        if value and value not in unique:
            unique.append(value)
    return unique
