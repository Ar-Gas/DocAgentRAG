import asyncio
import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.auth as auth_api  # noqa: E402
import api.dependencies as api_dependencies  # noqa: E402


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
