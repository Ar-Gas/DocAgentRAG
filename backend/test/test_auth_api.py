import asyncio
import json
import os
import sys
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api as api_module  # noqa: E402
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
        self.delete_auth_sessions_by_user_calls = []

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

    def delete_auth_sessions_by_user(self, user_id: str):
        self.delete_auth_sessions_by_user_calls.append(user_id)
        tokens = [
            token
            for token, session in self.sessions.items()
            if session["user_id"] == user_id
        ]
        for token in tokens:
            self.sessions.pop(token, None)

    def upsert_user(self, payload: dict):
        self.user.update(payload)
        return dict(self.user)


def create_test_client() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(auth_api.BusinessException, api_module.business_exception_handler)
    app.add_exception_handler(RequestValidationError, api_module.validation_exception_handler)
    app.add_exception_handler(Exception, api_module.generic_exception_handler)
    app.include_router(api_module.router, prefix="/api/v1")
    return app


def request_app(app: FastAPI, method: str, path: str, headers: dict | None = None) -> tuple[int, dict]:
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("latin-1"), str(value).encode("latin-1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }
    response = {"status": None, "body": b""}
    received = {"done": False}

    async def receive():
        if not received["done"]:
            received["done"] = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            response["status"] = message["status"]
        if message["type"] == "http.response.body":
            response["body"] += message.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return int(response["status"]), json.loads(response["body"].decode("utf-8"))


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


def test_extract_bearer_token_accepts_case_insensitive_scheme():
    assert api_dependencies.extract_bearer_token("bearer token-1") == "token-1"
    assert api_dependencies.extract_bearer_token("BEARER token-2") == "token-2"


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
            current_session={"token": "token-1", "user": {"id": "user-1"}},
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


def test_change_password_revokes_all_sessions_for_user():
    raw_user = {
        "id": "user-1",
        "username": "alice",
        "display_name": "Alice",
        "role_code": "employee",
        "status": "enabled",
    }
    store = FakeAuthStore(raw_user)
    service = AuthService(store=store)
    store.user["password_hash"] = service.hash_password("old123")
    store.create_auth_session("user-1", "token-1", "2099-01-01T00:00:00")
    store.create_auth_session("user-1", "token-2", "2099-01-01T00:00:00")
    store.create_auth_session("user-2", "token-3", "2099-01-01T00:00:00")

    service.change_password("user-1", "old123", "new123")

    assert store.delete_auth_sessions_by_user_calls == ["user-1"]
    assert set(store.sessions.keys()) == {"token-3"}
    assert service.verify_password("new123", store.user["password_hash"]) is True


def test_auth_me_request_without_token_returns_http_401():
    client = create_test_client()

    status_code, payload = request_app(client, "GET", "/api/v1/auth/me")

    assert status_code == 401
    assert payload == {"code": 401, "message": "未登录", "data": None}


def test_auth_logout_request_without_token_returns_http_401():
    client = create_test_client()

    status_code, payload = request_app(client, "POST", "/api/v1/auth/logout")

    assert status_code == 401
    assert payload == {"code": 401, "message": "未登录", "data": None}


def test_auth_me_request_accepts_case_insensitive_bearer_scheme(monkeypatch):
    class StubAuthService:
        def get_current_user(self, token: str):
            if token == "token-1":
                return {
                    "id": "user-1",
                    "username": "alice",
                    "display_name": "Alice",
                    "role_code": "employee",
                }
            return None

    monkeypatch.setattr(api_dependencies, "auth_service", StubAuthService())
    client = create_test_client()

    status_code, payload = request_app(
        client,
        "GET",
        "/api/v1/auth/me",
        headers={"Authorization": "bearer token-1"},
    )

    assert status_code == 200
    assert payload["data"]["username"] == "alice"


def test_auth_logout_request_parses_authorization_once(monkeypatch):
    parse_call_count = {"count": 0}
    original_extract = api_dependencies.extract_bearer_token

    def counting_extract(authorization: str) -> str:
        parse_call_count["count"] += 1
        return original_extract(authorization)

    class StubAuthService:
        def __init__(self):
            self.logged_out = []

        def get_current_user(self, token: str):
            if token == "token-1":
                return {
                    "id": "user-1",
                    "username": "alice",
                    "display_name": "Alice",
                    "role_code": "employee",
                }
            return None

        def logout(self, token: str):
            self.logged_out.append(token)

    stub = StubAuthService()
    monkeypatch.setattr(api_dependencies, "extract_bearer_token", counting_extract)
    monkeypatch.setattr(api_dependencies, "auth_service", stub)
    monkeypatch.setattr(auth_api, "auth_service", stub)
    client = create_test_client()

    status_code, payload = request_app(
        client,
        "POST",
        "/api/v1/auth/logout",
        headers={"Authorization": "Bearer token-1"},
    )

    assert status_code == 200
    assert payload["message"] == "退出成功"
    assert stub.logged_out == ["token-1"]
    assert parse_call_count["count"] == 1


def test_login_api_records_login_success_audit_with_ip(monkeypatch):
    login_payload = {
        "token": "token-1",
        "expires_at": "2026-04-16T00:00:00",
        "user": {
            "id": "user-1",
            "username": "alice",
            "display_name": "Alice",
            "role_code": "employee",
            "primary_department_id": "dept-fin",
        },
    }
    mock_login = Mock(return_value=login_payload)
    mock_record = Mock(return_value="audit-1")
    request = Mock(client=Mock(host="203.0.113.10"))
    monkeypatch.setattr(auth_api.auth_service, "login", mock_login)
    monkeypatch.setattr(auth_api, "audit_service", Mock(record=mock_record), raising=False)

    body = asyncio.run(
        auth_api.login(
            auth_api.LoginRequest(username="alice", password="secret123"),
            http_request=request,
        )
    )

    assert body["code"] == 200
    mock_record.assert_called_once_with(
        action_type="login_success",
        target_type="auth",
        target_id="user-1",
        result="success",
        user=login_payload["user"],
        ip_address="203.0.113.10",
        metadata={"username": "alice"},
    )


def test_login_api_records_login_failure_audit_with_ip(monkeypatch):
    mock_login = Mock(side_effect=auth_api.AppServiceError(4001, "用户名或密码错误"))
    mock_record = Mock(return_value="audit-1")
    request = Mock(client=Mock(host="198.51.100.20"))
    monkeypatch.setattr(auth_api.auth_service, "login", mock_login)
    monkeypatch.setattr(auth_api, "audit_service", Mock(record=mock_record), raising=False)

    try:
        asyncio.run(
            auth_api.login(
                auth_api.LoginRequest(username="alice", password="bad-password"),
                http_request=request,
            )
        )
    except auth_api.BusinessException as exc:
        assert exc.code == 4001
        assert exc.message == "用户名或密码错误"
    else:
        raise AssertionError("login should raise business exception")

    mock_record.assert_called_once_with(
        action_type="login_failure",
        target_type="auth",
        target_id="alice",
        result="failed",
        user={
            "id": None,
            "username": "alice",
            "role_code": "anonymous",
            "primary_department_id": None,
        },
        ip_address="198.51.100.20",
        metadata={
            "username": "alice",
            "error_code": 4001,
            "error_detail": "用户名或密码错误",
        },
    )
