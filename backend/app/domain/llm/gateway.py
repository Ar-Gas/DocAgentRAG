"""LLM Gateway - 统一的 LLM 调用入口
提供：缓存、重试、超时、token 追踪、provider fallback
"""
import json
import hashlib
import asyncio
import time
from typing import Optional, Dict, Any, List, AsyncIterator
from collections import OrderedDict
from dataclasses import dataclass

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logger import logger
from app.domain.llm.config import LLMConfig
from app.domain.llm import prompts


@dataclass
class LLMResponse:
    """LLM 响应封装"""
    content: str
    tokens_used: int = 0
    model: str = ""
    cached: bool = False


class SemanticCache:
    """简单的语义缓存实现（基于 LRU）"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 600):
        self.cache: OrderedDict[str, tuple] = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.timestamps: Dict[str, float] = {}

    def _hash_prompt(self, prompt: str) -> str:
        """对 prompt 进行哈希（简单的相同性判断，非真正的语义相似度）"""
        return hashlib.md5(prompt.encode()).hexdigest()

    def get(self, prompt: str) -> Optional[LLMResponse]:
        """获取缓存"""
        key = self._hash_prompt(prompt)
        if key not in self.cache:
            return None

        # 检查 TTL
        if time.time() - self.timestamps.get(key, 0) > self.ttl_seconds:
            del self.cache[key]
            del self.timestamps[key]
            return None

        # 移到末尾（LRU）
        self.cache.move_to_end(key)
        cached_response = self.cache[key]
        return LLMResponse(
            content=cached_response[0],
            tokens_used=cached_response[1],
            cached=True
        )

    def set(self, prompt: str, response: LLMResponse) -> None:
        """设置缓存"""
        key = self._hash_prompt(prompt)
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = (response.content, response.tokens_used)
        self.timestamps[key] = time.time()

        # 如果超过大小限制，删除最旧的
        if len(self.cache) > self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            del self.timestamps[oldest_key]

    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()
        self.timestamps.clear()


class LLMGateway:
    """统一的 LLM 调用网关"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.cache = SemanticCache(
            max_size=self.config.cache_max_size,
            ttl_seconds=self.config.cache_ttl_seconds
        ) if self.config.semantic_cache_enabled else None
        self.token_stats: Dict[str, int] = {
            "total": 0,
            "extract": 0,
            "classify": 0,
            "rerank": 0,
            "qa": 0,
            "analyze": 0,
            "summarize": 0,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _call_doubao(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 500,
        temperature: float = 0.7
    ) -> LLMResponse:
        """调用豆包 LLM API"""
        if not self.config.api_key:
            logger.warning("未配置 DOUBAO_API_KEY，LLM 调用不可用")
            raise ValueError("LLM API Key not configured")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        try:
            response = requests.post(
                self.config.api_url,
                headers=headers,
                json=payload,
                timeout=30  # 外层总超时
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                tokens_used = result.get("usage", {}).get("total_tokens", 0)
                return LLMResponse(
                    content=content,
                    tokens_used=tokens_used,
                    model=model,
                    cached=False
                )
            else:
                logger.error(f"豆包 API 返回 {response.status_code}: {response.text}")
                raise requests.RequestException(f"API error: {response.status_code}")

        except requests.exceptions.Timeout:
            logger.error("豆包 API 调用超时")
            raise
        except Exception as e:
            logger.error(f"豆包 API 调用失败: {str(e)}")
            raise

    async def call(
        self,
        prompt: str,
        task: str = "extract",
        max_tokens: int = 500,
        temperature: float = 0.7,
        use_cache: bool = True
    ) -> LLMResponse:
        """
        统一的 LLM 调用接口

        Args:
            prompt: 提示词
            task: 任务类型（extract, classify, rerank, qa, analyze, summarize）
            max_tokens: 最大输出 token 数
            temperature: 温度参数
            use_cache: 是否使用缓存

        Returns:
            LLMResponse: 包含内容、token 数、模型名、缓存标记
        """
        # 尝试从缓存获取
        if use_cache and self.cache:
            cached = self.cache.get(prompt)
            if cached:
                logger.debug(f"LLM 缓存命中：task={task}")
                self.token_stats[task] += cached.tokens_used
                return cached

        model = self.config.get_model(task)
        timeout = self.config.get_timeout(task)

        logger.info(f"调用 LLM: task={task}, model={model}, timeout={timeout}s")

        try:
            # 在 asyncio 中运行同步调用
            response = await asyncio.to_thread(
                self._call_doubao,
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature
            )

            # 存入缓存
            if use_cache and self.cache:
                self.cache.set(prompt, response)

            # 更新 token 统计
            self.token_stats["total"] += response.tokens_used
            self.token_stats[task] += response.tokens_used

            logger.info(f"LLM 调用成功: task={task}, tokens={response.tokens_used}")
            return response

        except Exception as e:
            logger.error(f"LLM 调用失败: {str(e)}")
            raise

    async def stream(
        self,
        prompt: str,
        task: str = "qa",
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> AsyncIterator[str]:
        """
        流式调用 LLM，逐个 yield 响应内容
        """
        # 豆包 API 目前可能不支持流式，先用分块输出
        response = await self.call(prompt, task, max_tokens, temperature, use_cache=False)
        for chunk in response.content:
            yield chunk
            await asyncio.sleep(0.01)  # 模拟流式间隔

    async def extract(self, text: str, extract_type: str = "metadata") -> Dict[str, Any]:
        """
        LLM 结构化抽取

        Args:
            text: 文本内容
            extract_type: 抽取类型（metadata, entities, kg_triples）

        Returns:
            结构化数据（通常是 dict 或 list）
        """
        if extract_type == "metadata":
            prompt = prompts.format_extraction_prompt(text)
        elif extract_type == "entities":
            prompt = prompts.format_entity_extraction_prompt(text)
        elif extract_type == "kg_triples":
            prompt = prompts.format_kg_extraction_prompt(text)
        else:
            raise ValueError(f"Unknown extract_type: {extract_type}")

        response = await self.call(prompt, task="extract")

        try:
            # 尝试解析 JSON
            return json.loads(response.content)
        except json.JSONDecodeError:
            logger.error(f"LLM 输出不是有效的 JSON: {response.content[:200]}")
            return {}

    async def classify(self, title: str, text: str, candidates: Optional[List[str]] = None) -> str:
        """
        LLM 分类

        Args:
            title: 文档标题
            text: 文档内容
            candidates: 可选的候选标签列表

        Returns:
            分类标签
        """
        prompt = prompts.format_classify_prompt(title, text)
        response = await self.call(prompt, task="classify", max_tokens=50)
        return response.content.strip()

    async def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """
        LLM rerank 文档

        Args:
            query: 查询
            documents: 文档列表（每个文档需要有 id 和 content）
            top_k: 返回前 k 个

        Returns:
            排序后的文档列表
        """
        doc_str = "\n".join([
            f"- [{doc.get('id', i)}] {doc.get('content', '')[:200]}"
            for i, doc in enumerate(documents[:20])
        ])

        prompt = prompts.RERANK_PROMPT.format(query=query, documents=doc_str)
        response = await self.call(prompt, task="rerank", max_tokens=500)

        try:
            ranked = json.loads(response.content)
            # 根据排序结果重新排列原始文档
            ranked_docs = []
            for item in ranked[:top_k]:
                doc_id = item.get("doc_id")
                for doc in documents:
                    if doc.get("id") == doc_id:
                        doc["_rerank_score"] = item.get("score", 0)
                        ranked_docs.append(doc)
                        break
            return ranked_docs
        except Exception as e:
            logger.error(f"Rerank 结果解析失败: {str(e)}")
            return documents[:top_k]

    async def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        查询意图分析

        Args:
            query: 用户查询

        Returns:
            结构化的查询分析结果
        """
        prompt = prompts.format_query_analysis_prompt(query)
        response = await self.call(prompt, task="analyze", max_tokens=300)

        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            logger.error(f"查询分析失败，返回原始查询")
            return {
                "intent": "事实查找",
                "expanded_queries": [query],
                "entity_filters": [],
                "time_filter": None,
                "doc_type_hint": None
            }

    async def arbitrate_labels(self, text: str, label_a: str, label_b: str) -> Dict[str, Any]:
        """
        分类仲裁：比较两个分类结果，选择最合适的

        Args:
            text: 文档内容
            label_a: 路径 A 的标签
            label_b: 路径 B 的标签

        Returns:
            仲裁结果（标签、置信度、理由）
        """
        prompt = prompts.format_arbitrate_prompt(text, label_a, label_b)
        response = await self.call(prompt, task="classify", max_tokens=200)

        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            # fallback：如果 label_a 和 label_b 相同，返回该标签
            if label_a == label_b:
                return {
                    "final_label": label_a,
                    "confidence": 1.0,
                    "reason": "两路分类结果一致"
                }
            return {
                "final_label": label_a,
                "confidence": 0.5,
                "reason": "使用路径A的结果"
            }

    def get_token_stats(self) -> Dict[str, int]:
        """获取 token 使用统计"""
        return self.token_stats.copy()

    def reset_token_stats(self) -> None:
        """重置 token 统计"""
        for key in self.token_stats:
            self.token_stats[key] = 0

    def clear_cache(self) -> None:
        """清空缓存"""
        if self.cache:
            self.cache.clear()
