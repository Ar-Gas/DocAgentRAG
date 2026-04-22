from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def build_document_profile(filename: str, file_type: str, content_length: int, estimated_chunks: int) -> dict:
    size_class = "small"
    defer_rag = False
    if estimated_chunks >= 500 or content_length >= 500000:
        size_class = "xlarge"
        defer_rag = True
    elif estimated_chunks >= 120 or content_length >= 120000:
        size_class = "large"
    elif estimated_chunks >= 40 or content_length >= 40000:
        size_class = "medium"

    return {
        "filename": filename,
        "file_type": file_type,
        "content_length": int(content_length or 0),
        "estimated_chunks": int(estimated_chunks or 0),
        "size_class": size_class,
        "defer_rag": defer_rag,
    }


@dataclass
class RagCircuitBreaker:
    failure_threshold: int = 3
    failure_count: int = 0
    last_error_code: str | None = None
    last_failure_at: str | None = None

    def record_failure(self, error_code: str) -> None:
        self.failure_count += 1
        self.last_error_code = error_code
        self.last_failure_at = datetime.utcnow().isoformat()

    def record_success(self) -> None:
        self.failure_count = 0
        self.last_error_code = None
        self.last_failure_at = None

    def is_open(self) -> bool:
        return self.failure_count >= self.failure_threshold

    def snapshot(self) -> dict:
        return {
            "open": self.is_open(),
            "failure_count": self.failure_count,
            "last_error_code": self.last_error_code,
            "last_failure_at": self.last_failure_at,
        }
