from dataclasses import dataclass, field
from typing import Any, Dict

from utils.document_processor import process_document


@dataclass
class ExtractionResult:
    success: bool
    content: str
    error: str | None = None
    parser_name: str | None = None
    preview_content: str = ""
    full_content_length: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExtractionService:
    def extract(self, filepath: str) -> ExtractionResult:
        success, content = process_document(filepath)
        parser_name = filepath.split(".")[-1].lower() if "." in filepath else None
        if success:
            preview = content[:1000] if len(content) > 1000 else content
            return ExtractionResult(
                success=True,
                content=content,
                parser_name=parser_name,
                preview_content=preview,
                full_content_length=len(content),
                metadata={"filepath": filepath},
            )
        return ExtractionResult(
            success=False,
            content="",
            error=content,
            parser_name=parser_name,
            metadata={"filepath": filepath},
        )
