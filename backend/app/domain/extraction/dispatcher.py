"""Extraction dispatcher - 按文件类型分派抽取器"""
from pathlib import Path
from typing import Optional
from app.domain.extraction.base import ExtractorBase, RawContent
from app.core.logger import logger


class ExtractionDispatcher:
    """根据文件类型分派到对应的抽取器"""

    def __init__(self):
        # 暂时保留现有 utils 中的抽取逻辑作为 fallback
        self.extractors: dict[str, ExtractorBase] = {}

    def register(self, mime_type: str, extractor: ExtractorBase) -> None:
        """注册抽取器"""
        self.extractors[mime_type] = extractor

    def extract(self, file_path: str) -> RawContent:
        """
        分派文件抽取

        Args:
            file_path: 文件路径

        Returns:
            RawContent: 原始内容
        """
        ext = Path(file_path).suffix.lower()
        mime_type_map = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain',
            '.eml': 'message/rfc822',
        }

        mime_type = mime_type_map.get(ext, 'application/octet-stream')

        # 寻找支持该类型的抽取器
        for registered_mime, extractor in self.extractors.items():
            if extractor.supports(mime_type):
                logger.info(f"使用 {extractor.__class__.__name__} 抽取 {file_path}")
                return extractor.extract(file_path)

        # 如果没有注册的抽取器，使用现有的 utils 逻辑（兼容性）
        logger.warning(f"未找到 {mime_type} 的抽取器，使用 utils 逻辑")
        from utils.document_processor import DocumentProcessor
        processor = DocumentProcessor()
        text = processor.extract_text(file_path)
        return RawContent(text=text, metadata={"file_path": file_path, "mime_type": mime_type})
