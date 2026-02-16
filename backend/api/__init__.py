from fastapi import APIRouter
from .classification import router as classification_router
from .document import router as document_router
from .retrieval import router as retrieval_router

# 创建主路由
router = APIRouter()

# 包含子路由
router.include_router(classification_router, prefix="/classification", tags=["分类"])
router.include_router(document_router, prefix="/document", tags=["文档"])
router.include_router(retrieval_router, prefix="/retrieval", tags=["检索"])
