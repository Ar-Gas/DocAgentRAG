from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.services.errors import AppServiceError
from app.services.organization_service import organization_service
from api import BusinessException, paginated, success
from api.dependencies import require_authenticated_user

router = APIRouter()


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role_code: str
    primary_department_id: str
    collaborative_department_ids: list[str] = Field(default_factory=list)
    status: str = "enabled"


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        created_user = organization_service.create_user(
            request.model_dump(),
            current_user=current_user,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=created_user, message="用户创建成功")


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=500, description="每页数量"),
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        page_data = organization_service.list_users(page, page_size, current_user=current_user)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return paginated(
        items=page_data["items"],
        total=page_data["total"],
        page=page_data["page"],
        page_size=page_data["page_size"],
    )


@router.get("/departments")
async def list_departments(current_user: dict = Depends(require_authenticated_user)):
    try:
        departments = organization_service.list_departments(current_user=current_user)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=departments)


@router.get("/roles")
async def list_roles(current_user: dict = Depends(require_authenticated_user)):
    try:
        roles = organization_service.list_roles(current_user=current_user)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return success(data=roles)
