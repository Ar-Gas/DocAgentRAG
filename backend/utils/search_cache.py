"""
检索结果 LRU 缓存（内存级）。

特性：
- 线程安全
- 容量：200 条
- TTL：300 秒
- 文档变更时全清（简单策略）
- key = MD5(query + mode + filters)
"""
import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

_DEFAULT_MAX_SIZE = 200
_DEFAULT_TTL = 300  # seconds


class SearchLRUCache:
    def __init__(self, max_size: int = _DEFAULT_MAX_SIZE, ttl: int = _DEFAULT_TTL):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Key 生成
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(query: str, mode: str, filters: dict) -> str:
        payload = {"q": query, "m": mode, "f": sorted(filters.items()) if filters else []}
        return hashlib.md5(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    # ------------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------------

    def get(self, query: str, mode: str, filters: dict) -> Optional[Any]:
        key = self.make_key(query, mode, filters)
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            value, ts = self._cache[key]
            if time.time() - ts > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            # LRU: 移到末尾
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, query: str, mode: str, filters: dict, value: Any) -> None:
        key = self.make_key(query, mode, filters)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, time.time())
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)  # 淘汰最旧

    # ------------------------------------------------------------------
    # 失效
    # ------------------------------------------------------------------

    def invalidate_all(self) -> None:
        """文档变更时全清缓存"""
        with self._lock:
            self._cache.clear()

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
            }


# 全局单例
_cache = SearchLRUCache()


def get_search_cache() -> SearchLRUCache:
    return _cache
