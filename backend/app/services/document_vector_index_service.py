import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.logger import logger
from app.infra.repositories.document_content_repository import DocumentContentRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from utils.document_processor import process_document


class DocumentVectorIndexService:
    def __init__(
        self,
        *,
        document_repository: Optional[DocumentRepository] = None,
        content_repository: Optional[DocumentContentRepository] = None,
        segment_repository: Optional[DocumentSegmentRepository] = None,
    ):
        self.document_repository = document_repository or DocumentRepository()
        self.content_repository = content_repository or DocumentContentRepository()
        self.segment_repository = segment_repository or DocumentSegmentRepository()

    def save_document_summary_for_classification(
        self,
        filepath,
        full_content: Optional[str] = None,
        parser_name: Optional[str] = None,
        display_filename: Optional[str] = None,
    ):
        filepath_path = Path(filepath) if filepath else None
        if not filepath_path or not filepath_path.exists():
            logger.error("保存摘要失败：文件不存在 {}", filepath)
            return None, None
        try:
            document_id = str(uuid.uuid4())
            filename = display_filename or filepath_path.name
            ext = filepath_path.suffix.lower()
            content = full_content
            if content is None:
                success, content = process_document(filepath)
                if not success:
                    logger.error("文档内容无效：{}", filepath)
                    return None, None

            preview_content = content[:1000] if len(content) > 1000 else content
            mtime = filepath_path.stat().st_mtime
            doc_info = {
                "id": document_id,
                "filename": filename,
                "filepath": filepath,
                "file_type": ext,
                "preview_content": preview_content,
                "full_content_length": len(content),
                "parser_name": parser_name or ext.lstrip("."),
                "extraction_status": "ready",
                "created_at": mtime,
                "created_at_iso": datetime.fromtimestamp(mtime).isoformat(),
            }
            if self.document_repository.upsert(doc_info):
                self.content_repository.save(
                    document_id,
                    full_content=content,
                    preview_content=preview_content,
                    extraction_status="ready",
                    parser_name=parser_name or ext.lstrip("."),
                )
                return document_id, doc_info
            return None, None
        except Exception as exc:
            logger.opt(exception=exc).error("保存文档摘要失败 filepath={}", filepath)
            return None, None
