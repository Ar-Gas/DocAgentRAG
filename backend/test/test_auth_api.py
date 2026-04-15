import asyncio
import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.auth as auth_api  # noqa: E402
import api.dependencies as api_dependencies  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402


INTERNAL_USER_FIELDS = {
    "password_hash",
    "status",
    "primary_department_id",
    "last_login_at",
    "external_identity_id",
    "created_at",
    "updated_at",
}


class FakeAuthStore:
    def __init__(self, user: dict):
        self.user = dict(user)
        self.sessions = {}

    def get_user_by_username(self, username: str):
        if username == self.user.get("username"):
            return dict(self.user)
        return None

    def create_auth_session(self, user_id: str, token: str, expires_at: str):
        self.sessions[token] = {"token": token, "user_id": user_id, "expires_at": expires_at}
        return token

    def touch_user_last_login(self, user_id: str, last_login_at: str):
        if user_id == self.user.get("id"):
            self.user["last_login_at"] = last_login_at

    def get_auth_session(self, token: str):
        return self.sessions.get(token)

    def get_user(self, user_id: str):
        if user_id == self.user.get("id"):
            return dict(self.user)
        return None

    def delete_auth_session(self, token: str):
        self.sessions.pop(token, None)


def test_login_api_returns_token_and_user_payload(monkeypatch):
    monkeypatch.setattr(
        auth_api.auth_service,
        "login",
        Mock(
            return_value={
                "token": "token-1",
                "expires_at": "2026-04-16T00:00:00",
                "user": {
                    "id": "user-1",
                    "username": "alice",
                    "display_name": "Alice",
                    "role_code": "employee",
                },
            }
        ),
    )

    body = asyncio.run(
        auth_api.login(auth_api.LoginRequest(username="alice", password="secret123"))
    )

    assert body["code"] == 200
    assert body["data"]["token"] == "token-1"
    assert body["data"]["user"]["username"] == "alice"


def test_require_authenticated_user_rejects_missing_bearer_token():
    try:
        asyncio.run(api_dependencies.require_authenticated_user(""))
    except auth_api.BusinessException as exc:
        assert exc.code == 401
    else:
        raise AssertionError("missing bearer token should fail")


def test_extract_bearer_token_returns_trimmed_token():
    token = api_dependencies.extract_bearer_token("Bearer token-1   ")
    assert token == "token-1"


def test_require_authenticated_user_returns_user(monkeypatch):
    mock_get_current_user = Mock(return_value={"id": "user-1", "username": "alice"})
    monkeypatch.setattr(api_dependencies.auth_service, "get_current_user", mock_get_current_user)

    user = asyncio.run(api_dependencies.require_authenticated_user("Bearer token-1"))

    assert user["id"] == "user-1"
    mock_get_current_user.assert_called_once_with("token-1")


def test_logout_api_deletes_current_token(monkeypatch):
    mock_logout = Mock()
    monkeypatch.setattr(auth_api.auth_service, "logout", mock_logout)

    body = asyncio.run(
        auth_api.logout(
            authorization="Bearer token-1",
            current_user={"id": "user-1"},
        )
    )

    assert body["code"] == 200
    assert body["message"] == "退出成功"
    mock_logout.assert_called_once_with("token-1")


def test_me_api_returns_current_user():
    body = asyncio.run(auth_api.me(current_user={"id": "user-1", "username": "alice"}))

    assert body["code"] == 200
    assert body["data"]["username"] == "alice"


def test_change_password_calls_service(monkeypatch):
    mock_change_password = Mock()
    monkeypatch.setattr(auth_api.auth_service, "change_password", mock_change_password)

    body = asyncio.run(
        auth_api.change_password(
            request=auth_api.ChangePasswordRequest(old_password="old123", new_password="new123"),
            current_user={"id": "user-1"},
        )
    )

    assert body["code"] == 200
    assert body["message"] == "密码修改成功"
    mock_change_password.assert_called_once_with("user-1", "old123", "new123")


def test_login_api_hides_internal_user_fields(monkeypatch):
    raw_user = {
        "id": "user-1",
        "username": "alice",
        "display_name": "Alice",
        "role_code": "employee",
        "status": "enabled",
        "primary_department_id": "dept-1",
        "last_login_at": "2026-04-15T00:00:00",
        "external_identity_id": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-04-15T00:00:00",
    }
    store = FakeAuthStore(raw_user)
    service = AuthService(store=store)
    store.user["password_hash"] = service.hash_password("secret123")
    monkeypatch.setattr(auth_api, "auth_service", service)

    body = asyncio.run(
        auth_api.login(auth_api.LoginRequest(username="alice", password="secret123"))
    )
    user = body["data"]["user"]

    assert body["code"] == 200
    assert user == {
        "id": "user-1",
        "username": "alice",
        "display_name": "Alice",
        "role_code": "employee",
    }
    assert not (INTERNAL_USER_FIELDS & set(user.keys()))


def test_me_api_hides_internal_user_fields_from_dependency(monkeypatch):
    raw_user = {
        "id": "user-1",
        "username": "alice",
        "display_name": "Alice",
        "role_code": "employee",
        "password_hash": "salt$hash",
        "status": "enabled",
        "primary_department_id": "dept-1",
        "last_login_at": "2026-04-15T00:00:00",
        "external_identity_id": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-04-15T00:00:00",
    }
    store = FakeAuthStore(raw_user)
    service = AuthService(store=store)
    store.create_auth_session(
        user_id="user-1",
        token="token-1",
        expires_at="2099-01-01T00:00:00",
    )
    monkeypatch.setattr(api_dependencies, "auth_service", service)

    current_user = asyncio.run(api_dependencies.require_authenticated_user("Bearer token-1"))
    body = asyncio.run(auth_api.me(current_user=current_user))

    assert body["code"] == 200
    assert body["data"] == {
        "id": "user-1",
        "username": "alice",
        "display_name": "Alice",
        "role_code": "employee",
    }
    assert not (INTERNAL_USER_FIELDS & set(body["data"].keys()))
