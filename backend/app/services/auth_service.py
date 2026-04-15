import hashlib
import secrets
from datetime import datetime, timedelta

from app.infra.metadata_store import get_metadata_store
from app.services.errors import AppServiceError


class AuthService:
    def __init__(self, store=None):
        self.store = store or get_metadata_store()

    def hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        return f"{salt.hex()}${digest.hex()}"

    def _to_public_user(self, user: dict) -> dict:
        return {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role_code": user["role_code"],
        }

    def get_audit_actor_snapshot(self, user_id: str | None) -> dict | None:
        if not user_id:
            return None
        user = self.store.get_user(user_id)
        if not user:
            return None
        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "role_code": user.get("role_code"),
            "primary_department_id": user.get("primary_department_id"),
        }

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            salt_hex, digest_hex = password_hash.split("$", 1)
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                120_000,
            )
            return secrets.compare_digest(digest.hex(), digest_hex)
        except Exception:
            return False

    def login(self, username: str, password: str) -> dict:
        user = self.store.get_user_by_username(username)
        if not user or user.get("status") != "enabled":
            raise AppServiceError(4001, "用户名或密码错误")
        if not self.verify_password(password, user.get("password_hash", "")):
            raise AppServiceError(4001, "用户名或密码错误")

        token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        expires_at = (now + timedelta(hours=12)).isoformat()
        self.store.create_auth_session(user_id=user["id"], token=token, expires_at=expires_at)
        self.store.touch_user_last_login(user["id"], now.isoformat())

        return {
            "token": token,
            "expires_at": expires_at,
            "user": self.get_current_user(token),
        }

    def get_current_user(self, token: str) -> dict | None:
        if not token:
            return None

        session = self.store.get_auth_session(token)
        if not session:
            return None

        try:
            expires_at = datetime.fromisoformat(session["expires_at"])
        except Exception:
            self.store.delete_auth_session(token)
            return None

        if expires_at <= datetime.utcnow():
            self.store.delete_auth_session(token)
            return None

        user = self.store.get_user(session["user_id"])
        if not user or user.get("status") != "enabled":
            return None
        return self._to_public_user(user)

    def logout(self, token: str) -> None:
        self.store.delete_auth_session(token)

    def change_password(self, user_id: str, old_password: str, new_password: str) -> None:
        user = self.store.get_user(user_id)
        if not user or not self.verify_password(old_password, user.get("password_hash", "")):
            raise AppServiceError(4002, "原密码错误")
        self.store.upsert_user({**user, "password_hash": self.hash_password(new_password)})
        self.store.delete_auth_sessions_by_user(user_id)
