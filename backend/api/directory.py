from fastapi import APIRouter, Depends, Query

from api import success
from api.dependencies import require_authenticated_user
from app.services.directory_service import DirectoryService

router = APIRouter()
directory_service = DirectoryService()


@router.get("/workspace", summary="获取目录工作区")
async def get_directory_workspace(
    visibility_scope: str | None = Query(None),
    department_id: str | None = Query(None),
    business_category_id: str | None = Query(None),
    current_user: dict = Depends(require_authenticated_user),
):
    payload = directory_service.build_workspace(
        visibility_scope=visibility_scope,
        department_id=department_id,
        business_category_id=business_category_id,
        current_user=current_user,
    )
    return success(data=payload)
