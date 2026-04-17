"""Chunking base - 切块策略基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class Chunk:
    """文本块"""
    content: str
    metadata: dict  # 包含 page_number, section_title 等


class ChunkStrategy(ABC):
    """切块策略基类"""

    @abstractmethod
    def chunk(self, text: str, metadata: dict = None) -> List[Chunk]:
        """
        对文本进行切块

        Args:
            text: 输入文本
            metadata: 元数据（文档信息等）

        Returns:
            切块结果
        """
        pass
