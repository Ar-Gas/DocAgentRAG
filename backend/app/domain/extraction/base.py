"""Extraction base - 抽取器基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class RawContent:
    """原始抽取内容"""
    text: str
    metadata: dict


class ExtractorBase(ABC):
    """文本抽取器基类"""

    @abstractmethod
    def extract(self, file_path: str) -> RawContent:
        """
        从文件中抽取文本

        Args:
            file_path: 文件路径

        Returns:
            RawContent: 原始内容和元数据
        """
        pass

    @abstractmethod
    def supports(self, mime_type: str) -> bool:
        """
        是否支持该 MIME 类型

        Args:
            mime_type: MIME 类型

        Returns:
            是否支持
        """
        pass
