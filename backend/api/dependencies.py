from fastapi import Header

from app.services.auth_service import AuthService
from api import BusinessException

auth_service = AuthService()


def extract_bearer_token(authorization: str) -> str:
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise BusinessException(code=401, message="未登录")
    token = authorization[len(prefix):].strip()
    if not token:
        raise BusinessException(code=401, message="未登录")
    return token


async def require_authenticated_user(authorization: str = Header(default="")) -> dict:
    token = extract_bearer_token(authorization)
    user = auth_service.get_current_user(token)
    if not user:
        raise BusinessException(code=401, message="未登录")
    return user
