"""Sliding window chunking - 滑动窗口切块"""
from typing import List
from app.domain.chunking.base import ChunkStrategy, Chunk


class SlidingWindowChunker(ChunkStrategy):
    """滑动窗口切块策略"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, metadata: dict = None) -> List[Chunk]:
        """使用滑动窗口进行切块"""
        if metadata is None:
            metadata = {}

        chunks = []
        step = self.chunk_size - self.overlap

        for i in range(0, len(text), step):
            chunk_text = text[i:i + self.chunk_size]
            if len(chunk_text.strip()) > 0:
                chunk = Chunk(
                    content=chunk_text,
                    metadata={
                        **metadata,
                        "chunk_index": len(chunks),
                        "start_pos": i,
                        "end_pos": min(i + self.chunk_size, len(text))
                    }
                )
                chunks.append(chunk)

        return chunks
