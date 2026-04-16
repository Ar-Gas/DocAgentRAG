from fastapi import Header

from app.services.auth_service import AuthService
from api import BusinessException

auth_service = AuthService()


def extract_bearer_token(authorization: str) -> str:
    if not authorization:
        raise BusinessException(code=401, message="未登录")
    scheme, _, token_part = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise BusinessException(code=401, message="未登录")
    token = token_part.strip()
    if not token:
        raise BusinessException(code=401, message="未登录")
    return token


async def require_authenticated_session(authorization: str = Header(default="")) -> dict:
    token = extract_bearer_token(authorization)
    user = auth_service.get_current_actor(token)
    if not user:
        raise BusinessException(code=401, message="未登录")
    return {"token": token, "user": user}


async def require_authenticated_user(authorization: str = Header(default="")) -> dict:
    session = await require_authenticated_session(authorization)
    return session["user"]
