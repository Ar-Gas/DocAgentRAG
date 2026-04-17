from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict
from typing import TypeVar, Optional, Generic, List, Any

from config import ERROR_CODES
from app.core.logger import get_request_id_from_request, logger

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: Optional[T] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

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


def _response_headers(request: Request) -> dict[str, str]:
    request_id = get_request_id_from_request(request)
    if request_id == "-":
        return {}
    return {"X-Request-ID": request_id}

async def business_exception_handler(request: Request, exc: BusinessException):
    request_id = get_request_id_from_request(request)
    logger.bind(request_id=request_id).warning(
        "business_exception code={} message={} detail={} method={} path={}",
        exc.code,
        exc.message,
        exc.detail,
        getattr(request, "method", "-"),
        request.url.path,
    )
    return JSONResponse(
        status_code=400,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": {"detail": exc.detail} if exc.detail else None
        },
        headers=_response_headers(request),
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"]
        })
    request_id = get_request_id_from_request(request)
    logger.bind(request_id=request_id).warning(
        "validation_failed errors={} method={} path={}",
        errors,
        getattr(request, "method", "-"),
        request.url.path,
    )
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "参数校验失败",
            "data": {"errors": errors}
        },
        headers=_response_headers(request),
    )

async def generic_exception_handler(request: Request, exc: Exception):
    request_id = get_request_id_from_request(request)
    logger.bind(request_id=request_id).opt(exception=exc).error(
        "unhandled_exception method={} path={} error={}",
        getattr(request, "method", "-"),
        request.url.path,
        str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "data": None
        },
        headers=_response_headers(request),
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
from .qa import router as qa_router
from .topics import router as topics_router
from .admin import router as admin_router

router = APIRouter()

router.include_router(document_router, prefix="/documents", tags=["文档管理"])
router.include_router(classification_router, prefix="/classification", tags=["智能分类"])
router.include_router(retrieval_router, prefix="/retrieval", tags=["语义检索"])
router.include_router(qa_router, prefix="/qa", tags=["文档问答"])
router.include_router(topics_router, prefix="/topics", tags=["知识图谱"])
router.include_router(admin_router, prefix="/admin", tags=["系统管理"])

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
