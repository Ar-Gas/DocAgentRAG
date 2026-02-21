from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import TypeVar, Optional, Generic, List, Any
import logging

from config import ERROR_CODES

logger = logging.getLogger(__name__)

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: Optional[T] = None

    class Config:
        arbitrary_types_allowed = True

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

class BusinessException(Exception):
    def __init__(self, code: int, message: str = None, detail: str = None):
        self.code = code
        self.message = message or ERROR_CODES.get(code, "未知错误")
        self.detail = detail

async def business_exception_handler(request: Request, exc: BusinessException):
    logger.error(f"业务异常: code={exc.code}, message={exc.message}, detail={exc.detail}")
    return JSONResponse(
        status_code=400,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": {"detail": exc.detail} if exc.detail else None
        }
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"]
        })
    logger.error(f"参数校验失败: {errors}")
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "参数校验失败",
            "data": {"errors": errors}
        }
    )

async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"系统异常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "data": None
        }
    )

def success(data: Any = None, message: str = "success") -> dict:
    return {
        "code": 200,
        "message": message,
        "data": data
    }

def fail(code: int, message: str = None, detail: str = None) -> dict:
    msg = message or ERROR_CODES.get(code, "操作失败")
    return {
        "code": code,
        "message": msg,
        "data": {"detail": detail} if detail else None
    }

def paginated(items: List[Any], total: int, page: int, page_size: int) -> dict:
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    }

from .document import router as document_router
from .classification import router as classification_router
from .retrieval import router as retrieval_router

router = APIRouter()

router.include_router(document_router, prefix="/documents", tags=["文档管理"])
router.include_router(classification_router, prefix="/classification", tags=["智能分类"])
router.include_router(retrieval_router, prefix="/retrieval", tags=["语义检索"])

__all__ = [
    "router", 
    "ApiResponse", 
    "PaginatedResponse", 
    "BusinessException",
    "success", 
    "fail", 
    "paginated",
    "business_exception_handler",
    "validation_exception_handler",
    "generic_exception_handler"
]
