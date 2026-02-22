
"""
查询解析器 - 支持百度式检索语法
支持精确匹配、模糊匹配、高级语法
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedQuery:
    """解析后的查询结构"""
    original_query: str
    exact_phrases: List[str]
    exclude_terms: List[str]
    include_terms: List[str]
    fuzzy_terms: List[str]
    file_types: List[str]
    date_range: Optional[Tuple[str, str]]
    is_advanced: bool = False


class SearchQueryParser:
    """检索查询解析器"""

    def __init__(self):
        pass

    def parse(self, query: str) -> ParsedQuery:
        """
        解析查询字符串，支持多种检索语法
        
        支持的语法：
        - "关键词" : 模糊匹配
        - "精确短语" : 精确匹配（双引号包裹）
        - -排除词 : 排除指定词
        - filetype:pdf : 文件类型过滤
        - ~模糊词~ : 模糊匹配（波浪线包裹）
        
        :param query: 原始查询字符串
        :return: ParsedQuery 对象
        """
        if not query or not query.strip():
            return ParsedQuery(
                original_query="",
                exact_phrases=[],
                exclude_terms=[],
                include_terms=[],
                fuzzy_terms=[],
                file_types=[],
                date_range=None
            )

        original_query = query.strip()

        # 提取精确短语（双引号包裹的内容）
        exact_phrases = []
        exact_pattern = r'"([^"]+)"'
        for match in re.finditer(exact_pattern, original_query):
            exact_phrases.append(match.group(1).strip())
        # 移除已提取的精确短语
        query_without_exact = re.sub(exact_pattern, '', original_query)

        # 提取排除词（-开头的词）
        exclude_terms = []
        exclude_pattern = r'-(\S+)'
        for match in re.finditer(exclude_pattern, query_without_exact):
            exclude_terms.append(match.group(1).strip())
        # 移除已提取的排除词
        query_without_exclude = re.sub(exclude_pattern, '', query_without_exact)

        # 提取文件类型过滤（filetype:xxx）
        file_types = []
        filetype_pattern = r'filetype:(\S+)'
        for match in re.finditer(filetype_pattern, query_without_exclude):
            ft = match.group(1).strip().lower().lstrip('.')
            if ft:
                file_types.append(ft)
        # 移除已提取的文件类型
        query_without_filetype = re.sub(filetype_pattern, '', query_without_exclude)

        # 提取模糊匹配（~xxx~）
        fuzzy_terms = []
        fuzzy_pattern = r'~([^~]+)~'
        for match in re.finditer(fuzzy_pattern, query_without_filetype):
            fuzzy_terms.append(match.group(1).strip())
        # 移除已提取的模糊词
        query_without_fuzzy = re.sub(fuzzy_pattern, '', query_without_filetype)

        # 剩余的作为普通包含词
        include_terms = self._extract_terms(query_without_fuzzy)

        # 判断是否为高级查询
        is_advanced = (
            len(exact_phrases) > 0 or
            len(exclude_terms) > 0 or
            len(file_types) > 0 or
            len(fuzzy_terms) > 0
        )

        parsed = ParsedQuery(
            original_query=original_query,
            exact_phrases=exact_phrases,
            exclude_terms=exclude_terms,
            include_terms=include_terms,
            fuzzy_terms=fuzzy_terms,
            file_types=file_types,
            date_range=None,
            is_advanced=is_advanced
        )

        logger.debug(f"查询解析结果: {parsed}")
        return parsed

    def _extract_terms(self, text: str) -> List[str]:
        """从文本中提取检索词"""
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        # 简单分词（支持中英文）
        terms = []
        try:
            import jieba
            terms = [w.strip() for w in jieba.lcut(text) if len(w.strip()) > 0]
        except ImportError:
            # 简单的正则分词
            terms = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z0-9]+', text)
            terms = [w for w in terms if len(w) > 0]
        return terms

    def get_search_string_for_bm25(self, parsed: ParsedQuery) -> str:
        """
        生成用于BM25检索的查询字符串"""
        parts = []
        parts.extend(parsed.include_terms)
        parts.extend(parsed.exact_phrases)
        parts.extend(parsed.fuzzy_terms)
        return ' '.join(parts)

    def get_search_string_for_vector(self, parsed: ParsedQuery) -> str:
        """
        生成用于向量检索的查询字符串"""
        parts = []
        parts.extend(parsed.include_terms)
        parts.extend(parsed.exact_phrases)
        return ' '.join(parts)

    def should_filter_exclude(self, content: str, parsed: ParsedQuery) -> bool:
        """
        判断内容是否应该被排除（基于排除词）"""
        if not parsed.exclude_terms:
            return False
        content_lower = content.lower()
        for term in parsed.exclude_terms:
            if term.lower() in content_lower:
                return True
        return False

    def has_exact_match(self, content: str, parsed: ParsedQuery) -> bool:
        """
        判断内容是否包含精确短语"""
        if not parsed.exact_phrases:
            return False
        content_lower = content.lower()
        for phrase in parsed.exact_phrases:
            if phrase.lower() in content_lower:
                return True
        return False

