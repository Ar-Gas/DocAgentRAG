from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.taxonomy.universal_taxonomy_v3 import get_label_by_path


@dataclass(frozen=True)
class ParsedClassification:
    path: list[str]
    label_id: str
    is_fallback: bool
    confidence: float
    reason: str


def parse_classification_output(raw_text: str) -> ParsedClassification | None:
    text = str(raw_text or "").strip()
    if not text:
        return None

    path = _extract_line_protocol_path(text) or _extract_inline_path(text)
    if not path:
        return None

    label = get_label_by_path(path)
    if not label:
        return None

    return ParsedClassification(
        path=list(label["path"]),
        label_id=str(label["id"]),
        is_fallback=_parse_fallback_flag(text),
        confidence=_parse_confidence(text),
        reason=_parse_reason(text),
    )


def _extract_line_protocol_path(text: str) -> list[str] | None:
    fields = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
        elif "：" in line:
            key, value = line.split("：", 1)
        else:
            continue
        fields[key.strip()] = value.strip()

    domain = fields.get("一级域")
    group = fields.get("二级类")
    leaf = fields.get("三级类")
    if domain and group and leaf:
        return [domain, group, leaf]
    return None


def _extract_inline_path(text: str) -> list[str] | None:
    cleaned = re.sub(r"^(类别|分类|路径|分类路径)\s*[:：]\s*", "", text).strip()
    parts = [part.strip() for part in cleaned.replace(">", "/").split("/") if part.strip()]
    if len(parts) == 3:
        return parts
    return None


def _parse_fallback_flag(text: str) -> bool:
    match = re.search(r"是否兜底\s*[:：]\s*(是|否|true|false|yes|no)", text, re.I)
    if not match:
        return False
    return match.group(1).lower() in {"是", "true", "yes"}


def _parse_confidence(text: str) -> float:
    match = re.search(r"置信度\s*[:：]\s*([0-9]+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    return max(0.0, min(float(match.group(1)), 1.0))


def _parse_reason(text: str) -> str:
    match = re.search(r"依据\s*[:：]\s*(.+)", text)
    if not match:
        return ""
    return match.group(1).strip()[:300]
