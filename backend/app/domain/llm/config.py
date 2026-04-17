"""LLM Gateway 配置"""
import os
from typing import Any, Dict

try:
    import config as _repo_config
except ModuleNotFoundError:
    _repo_config = None


def _get_setting(name: str, default: Any) -> Any:
    env_value = os.getenv(name)
    if env_value not in (None, ""):
        return env_value
    if _repo_config is not None:
        config_value = getattr(_repo_config, name, None)
        if config_value not in (None, ""):
            return config_value
    return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"

class LLMConfig:
    """LLM 统一配置，管理模型、超时、缓存等"""

    def __init__(self):
        # Provider 配置
        self.api_key = _get_setting("DOUBAO_API_KEY", "")
        self.api_url = _get_setting(
            "DOUBAO_LLM_API_URL",
            "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        )

        # 模型配置：按任务类型选择不同模型
        self.model_for_task: Dict[str, str] = {
            "extract": _get_setting("DOUBAO_MINI_LLM_MODEL", "doubao-seed-2-0-mini-260215"),
            "classify": _get_setting("DOUBAO_MINI_LLM_MODEL", "doubao-seed-2-0-mini-260215"),
            "rerank": _get_setting("DOUBAO_MINI_LLM_MODEL", "doubao-seed-2-0-mini-260215"),
            "qa": _get_setting("DOUBAO_LLM_MODEL", "doubao-pro-32k-241115"),
            "analyze": _get_setting("DOUBAO_MINI_LLM_MODEL", "doubao-seed-2-0-mini-260215"),
            "summarize": _get_setting("DOUBAO_LLM_MODEL", "doubao-pro-32k-241115"),
        }

        # 超时配置（秒）：按任务类型
        self.timeout_for_task: Dict[str, float] = {
            "extract": float(_get_setting("LLM_TIMEOUT_EXTRACT", "10")),
            "classify": float(_get_setting("LLM_TIMEOUT_CLASSIFY", "8")),
            "rerank": float(_get_setting("LLM_TIMEOUT_RERANK", "15")),
            "qa": float(_get_setting("LLM_TIMEOUT_QA", "30")),
            "analyze": float(_get_setting("LLM_TIMEOUT_ANALYZE", "10")),
            "summarize": float(_get_setting("LLM_TIMEOUT_SUMMARIZE", "20")),
        }

        # 重试配置
        self.max_retries = int(_get_setting("LLM_MAX_RETRIES", "3"))
        self.retry_backoff_factor = 2.0

        # 缓存配置
        self.semantic_cache_enabled = _as_bool(_get_setting("SEMANTIC_CACHE_ENABLED", "true"))
        self.cache_ttl_seconds = int(_get_setting("CACHE_TTL_SECONDS", "600"))
        self.cache_max_size = int(_get_setting("CACHE_MAX_SIZE", "1000"))

        # Token 追踪
        self.track_tokens = _as_bool(_get_setting("TRACK_LLM_TOKENS", "true"))

    def get_model(self, task: str) -> str:
        """获取任务对应的模型"""
        return self.model_for_task.get(task, self.model_for_task["extract"])

    def get_timeout(self, task: str) -> float:
        """获取任务对应的超时时间"""
        return self.timeout_for_task.get(task, 10.0)
