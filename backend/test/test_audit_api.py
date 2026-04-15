import asyncio
import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.audit as audit_api  # noqa: E402


def test_list_audit_logs_forwards_filters_and_paging(monkeypatch):
    current_user = {"id": "user-audit", "role_code": "audit_readonly"}
    mock_list_logs = Mock(
        return_value={
            "items": [
                {
                    "id": "audit-1",
                    "action_type": "login_success",
                    "target_type": "auth",
                    "target_id": "alice",
                    "result": "success",
                }
            ],
            "total": 1,
            "page": 3,
            "page_size": 20,
            "total_pages": 1,
        }
    )
    monkeypatch.setattr(audit_api.audit_service, "list_logs", mock_list_logs)

    body = asyncio.run(
        audit_api.list_audit_logs(
            page=3,
            page_size=20,
            action_type="login_success",
            result="success",
            target_type="auth",
            target_id="alice",
            user_id="user-alice",
            start_time="2026-04-01T00:00:00",
            end_time="2026-04-15T23:59:59",
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    assert body["data"]["items"][0]["action_type"] == "login_success"
    assert body["data"]["page"] == 3
    assert body["data"]["page_size"] == 20
    mock_list_logs.assert_called_once_with(
        page=3,
        page_size=20,
        action_type="login_success",
        result="success",
        target_type="auth",
        target_id="alice",
        user_id="user-alice",
        start_time="2026-04-01T00:00:00",
        end_time="2026-04-15T23:59:59",
        current_user=current_user,
    )
