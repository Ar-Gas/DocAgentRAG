"""Admin API - 系统管理端点"""
from fastapi import APIRouter

from app.core.logger import logger
from app.services.observability_service import ObservabilityService
from api import success, BusinessException

router = APIRouter()
obs_service = ObservabilityService()


@router.get("/stats", summary="获取系统统计")
async def get_system_stats():
    """获取系统运行统计信息"""
    try:
        stats = obs_service.get_system_stats()
        return success(data=stats, message="获取统计成功")

    except Exception as e:
        logger.error(f"获取统计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/llm-stats", summary="获取 LLM 调用统计")
async def get_llm_stats():
    """获取 LLM token 用量统计"""
    try:
        stats = obs_service.get_llm_stats()
        return success(data=stats, message="获取 LLM 统计成功")

    except Exception as e:
        logger.error(f"获取 LLM 统计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/cache-stats", summary="获取缓存统计")
async def get_cache_stats():
    """获取缓存使用统计"""
    try:
        stats = obs_service.get_cache_stats()
        return success(data=stats, message="获取缓存统计成功")

    except Exception as e:
        logger.error(f"获取缓存统计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.post("/reset-stats", summary="重置统计")
async def reset_stats():
    """重置所有统计信息"""
    try:
        obs_service.reset_stats()
        return success(message="统计已重置")

    except Exception as e:
        logger.error(f"重置统计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))
