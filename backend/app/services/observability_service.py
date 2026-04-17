"""Observability service - 系统可观测性"""
from typing import Dict, Any
from app.domain.llm.gateway import LLMGateway
from app.core.logger import logger


class ObservabilityService:
    """系统可观测性服务"""

    def __init__(self):
        self.llm_gateway = LLMGateway()

    def get_llm_stats(self) -> Dict[str, Any]:
        """获取 LLM 调用统计"""
        stats = self.llm_gateway.get_token_stats()

        return {
            "total_tokens": stats.get("total", 0),
            "by_task": {
                "extract": stats.get("extract", 0),
                "classify": stats.get("classify", 0),
                "rerank": stats.get("rerank", 0),
                "qa": stats.get("qa", 0),
                "analyze": stats.get("analyze", 0),
                "summarize": stats.get("summarize", 0),
            },
            "estimated_cost": self._estimate_cost(stats.get("total", 0))
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        cache = self.llm_gateway.cache
        if not cache:
            return {"enabled": False}

        return {
            "enabled": True,
            "cache_size": len(cache.cache),
            "max_size": cache.max_size,
            "ttl_seconds": cache.ttl_seconds
        }

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统整体统计"""
        return {
            "llm": self.get_llm_stats(),
            "cache": self.get_cache_stats(),
            "timestamp": self._get_timestamp()
        }

    def reset_stats(self) -> None:
        """重置统计信息"""
        self.llm_gateway.reset_token_stats()
        logger.info("系统统计已重置")

    @staticmethod
    def _estimate_cost(tokens: int) -> float:
        """估算成本（豆包定价示例）"""
        # 豆包定价：约 0.002 元 / 1k tokens
        return (tokens / 1000) * 0.002

    @staticmethod
    def _get_timestamp() -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
