from fastapi import APIRouter, Depends, Query

from app.services.audit_service import audit_service
from app.services.errors import AppServiceError
from api import BusinessException, paginated
from api.dependencies import require_authenticated_user

router = APIRouter()


@router.get("/audit-logs")
async def list_audit_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=500, description="每页数量"),
    action_type: str | None = Query(None, description="操作类型"),
    result: str | None = Query(None, description="执行结果"),
    target_type: str | None = Query(None, description="目标类型"),
    target_id: str | None = Query(None, description="目标 ID"),
    user_id: str | None = Query(None, description="操作者 ID"),
    username: str | None = Query(None, description="用户名快照"),
    start_time: str | None = Query(None, description="起始时间(ISO8601)"),
    end_time: str | None = Query(None, description="结束时间(ISO8601)"),
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        page_data = audit_service.list_logs(
            page=page,
            page_size=page_size,
            action_type=action_type,
            result=result,
            target_type=target_type,
            target_id=target_id,
            user_id=user_id,
            username=username,
            start_time=start_time,
            end_time=end_time,
            current_user=current_user,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail, detail=exc.detail)
    return paginated(
        items=page_data["items"],
        total=page_data["total"],
        page=page_data["page"],
        page_size=page_data["page_size"],
    )
