"""Structural chunking - 按文档结构切块"""
from typing import List
from app.domain.chunking.base import ChunkStrategy, Chunk


class StructuralChunker(ChunkStrategy):
    """按文档结构（标题、段落、表格）进行切块"""

    def __init__(self, max_chunk_size: int = 500, overlap: int = 50):
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    def chunk(self, text: str, metadata: dict = None) -> List[Chunk]:
        """按结构切块"""
        if metadata is None:
            metadata = {}

        # 使用现有的 semantic_segmenter 逻辑
        from utils.semantic_segmenter import SemanticSegmenter
        segmenter = SemanticSegmenter()
        segments = segmenter.segment(text)

        chunks = []
        for seg in segments:
            chunk = Chunk(
                content=seg.get("text", ""),
                metadata={
                    **metadata,
                    "segment_type": seg.get("type", "text"),
                    "title": seg.get("title", "")
                }
            )
            chunks.append(chunk)

        return chunks
