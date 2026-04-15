import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.services.audit_service import audit_service
from app.services.errors import AppServiceError
from api import BusinessException, success
from api.dependencies import (
    auth_service,
    require_authenticated_session,
    require_authenticated_user,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/login")
async def login(request: LoginRequest, http_request: Request = None):
    ip_address = None
    if http_request is not None and getattr(http_request, "client", None) is not None:
        ip_address = getattr(http_request.client, "host", None)

    try:
        login_result = auth_service.login(request.username, request.password)
        authenticated_user = login_result.get("user") or {}
        try:
            audit_service.record(
                action_type="login_success",
                target_type="auth",
                target_id=authenticated_user.get("id") or request.username,
                result="success",
                user=authenticated_user,
                ip_address=ip_address,
                metadata={"username": request.username},
            )
        except Exception:
            logger.exception("记录登录成功审计日志失败")
        return success(
            data=login_result,
            message="登录成功",
        )
    except AppServiceError as exc:
        try:
            audit_service.record(
                action_type="login_failure",
                target_type="auth",
                target_id=request.username,
                result="failed",
                user={
                    "id": None,
                    "username": request.username,
                    "role_code": "anonymous",
                    "primary_department_id": None,
                },
                ip_address=ip_address,
                metadata={
                    "username": request.username,
                    "error_code": exc.code,
                    "error_detail": exc.detail,
                },
            )
        except Exception:
            logger.exception("记录登录失败审计日志失败")
        raise BusinessException(code=exc.code, message=exc.detail)


@router.post("/logout")
async def logout(
    current_session: dict = Depends(require_authenticated_session),
):
    auth_service.logout(current_session["token"])
    return success(message="退出成功")


@router.get("/me")
async def me(current_user: dict = Depends(require_authenticated_user)):
    return success(data=current_user)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        auth_service.change_password(
            current_user["id"],
            request.old_password,
            request.new_password,
        )
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, message=exc.detail)
    return success(message="密码修改成功")
