"""Query analyzer - 查询结构化分析"""
import json
from dataclasses import dataclass
from typing import List, Optional
from app.domain.llm.gateway import LLMGateway
from app.core.logger import logger


@dataclass
class AnalyzedQuery:
    """结构化的查询分析结果"""
    intent: str  # 事实查找、定位、总结、比较
    expanded_queries: List[str]  # 扩展查询列表
    entity_filters: List[str]  # 实体过滤器
    time_filter: Optional[str]  # 时间范围
    doc_type_hint: Optional[str]  # 文档类型提示


class QueryAnalyzer:
    """使用 LLM 进行查询意图分析"""

    def __init__(self):
        self.llm_gateway = LLMGateway()

    async def analyze(self, query: str) -> AnalyzedQuery:
        """
        分析查询，返回结构化的意图信息

        Args:
            query: 用户查询

        Returns:
            AnalyzedQuery: 结构化的查询分析
        """
        try:
            result = await self.llm_gateway.analyze_query(query)

            return AnalyzedQuery(
                intent=result.get("intent", "事实查找"),
                expanded_queries=result.get("expanded_queries", [query]),
                entity_filters=result.get("entity_filters", []),
                time_filter=result.get("time_filter"),
                doc_type_hint=result.get("doc_type_hint")
            )
        except Exception as e:
            logger.error(f"Query 分析失败: {str(e)}")
            # Fallback：返回原始查询
            return AnalyzedQuery(
                intent="事实查找",
                expanded_queries=[query],
                entity_filters=[],
                time_filter=None,
                doc_type_hint=None
            )
