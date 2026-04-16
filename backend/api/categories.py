from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.services.category_service import category_service
from app.services.errors import AppServiceError
from api import BusinessException, success
from api.dependencies import require_authenticated_user

router = APIRouter()


class CreateSystemCategoryRequest(BaseModel):
    name: str
    sort_order: int = 0
    status: str = "enabled"


class CreateDepartmentCategoryRequest(BaseModel):
    name: str
    department_id: str
    sort_order: int = 0
    status: str = "enabled"


class UpdateCategoryRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    sort_order: int | None = None
    scope_type: str | None = None
    department_id: str | None = None


@router.post("/system")
async def create_system_category(
    request: CreateSystemCategoryRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        category = category_service.create_system_category(
            request.model_dump(),
            current_user=current_user,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=category, message="分类创建成功")


@router.get("/system")
async def list_system_categories(
    status: str | None = Query(None, description="状态过滤(enabled/disabled)"),
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        categories = category_service.list_system_categories(
            status=status,
            current_user=current_user,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=categories)


@router.post("/department")
async def create_department_category(
    request: CreateDepartmentCategoryRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        category = category_service.create_department_category(
            request.model_dump(),
            current_user=current_user,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=category, message="分类创建成功")


@router.get("/department")
async def list_department_categories(
    department_id: str = Query(..., description="部门 ID"),
    status: str | None = Query(None, description="状态过滤(enabled/disabled)"),
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        categories = category_service.list_department_categories(
            department_id=department_id,
            status=status,
            current_user=current_user,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=categories)


@router.patch("/{category_id}")
async def update_category(
    category_id: str,
    request: UpdateCategoryRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        category = category_service.update_category(
            category_id,
            request.model_dump(exclude_unset=True),
            current_user=current_user,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=category, message="分类更新成功")
