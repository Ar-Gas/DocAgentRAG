from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.errors import AppServiceError
from api import BusinessException, success
from api.dependencies import (
    auth_service,
    require_authenticated_session,
    require_authenticated_user,
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/login")
async def login(request: LoginRequest):
    try:
        return success(
            data=auth_service.login(request.username, request.password),
            message="登录成功",
        )
    except AppServiceError as exc:
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
