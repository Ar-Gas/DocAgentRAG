from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.services.category_service import category_service
from app.services.errors import AppServiceError
from api import BusinessException, success
from api.dependencies import require_authenticated_user

router = APIRouter()


class CreateCategoryRequest(BaseModel):
    name: str
    scope_type: str
    department_id: str | None = None
    sort_order: int = 0
    status: str = "enabled"


@router.post("/")
async def create_category(
    request: CreateCategoryRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        category = category_service.create_category(
            request.model_dump(),
            current_user=current_user,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=category, message="分类创建成功")


@router.get("/")
async def list_categories(
    scope_type: str | None = Query(None, description="分类范围(system/department)"),
    department_id: str | None = Query(None, description="部门 ID"),
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        categories = category_service.list_categories(
            scope_type=scope_type,
            department_id=department_id,
            current_user=current_user,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=categories)
