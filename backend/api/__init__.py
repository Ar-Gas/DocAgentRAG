# ===================== 优化1：调整导入顺序（第三方库在前，本地模块在后）=====================
from fastapi import APIRouter
from pydantic import BaseModel
from typing import TypeVar, Optional, Generic

# ===================== 优化2：移除重复的 TypeVar 导入 =====================
# 之前从 pydantic 和 typing 都导入了 TypeVar，重复了，只保留 typing 的即可
T = TypeVar("T")

# ===================== 统一响应模型（前端友好，所有接口返回格式一致）=====================
class ApiResponse(BaseModel, Generic[T]):
    """
    统一API响应模型
    所有接口都返回这个格式，前端不用每个接口写不同的解析逻辑
    """
    code: int = 200
    message: str = "success"
    data: Optional[T] = None

    class Config:
        # 优化3：允许任意类型，避免后续可能的类型错误
        arbitrary_types_allowed = True

# ===================== 导入子模块路由（放在统一响应模型后面，避免循环导入）=====================
from .document import router as document_router
from .classification import router as classification_router
from .retrieval import router as retrieval_router

# ===================== 总路由 =====================
router = APIRouter()

# ===================== 挂载子模块路由（按业务模块加前缀和标签，Swagger文档更清晰）=====================
router.include_router(document_router, prefix="/documents", tags=["文档管理"])
router.include_router(classification_router, prefix="/classification", tags=["智能分类"])
router.include_router(retrieval_router, prefix="/retrieval", tags=["语义检索"])

# ===================== 优化4：定义 __all__，方便其他模块导入 =====================
__all__ = ["router", "ApiResponse"]