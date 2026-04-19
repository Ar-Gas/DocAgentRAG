import asyncio
import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.admin as admin_api  # noqa: E402


def test_start_local_only_batch_import_api_registers_local_files_and_returns_task_status(monkeypatch):
    mock_register = Mock(return_value=4)
    mock_start = Mock(
        return_value={
            "job_id": "job-1",
            "state": "running",
            "total": 3,
            "concurrency": 2,
            "interval_seconds": 0.5,
            "already_running": False,
        }
    )
    monkeypatch.setattr(admin_api.document_audit_service, "register_local_only_documents", mock_register)
    monkeypatch.setattr(admin_api.document_service, "start_local_only_batch_import", mock_start)

    request = admin_api.LocalOnlyBatchImportRequest(
        limit=3,
        concurrency=2,
        interval_seconds=0.5,
        include_failed=True,
    )

    payload = asyncio.run(admin_api.start_local_only_batch_import(request))

    assert payload["code"] == 200
    assert payload["data"]["job_id"] == "job-1"
    assert payload["data"]["registered_local_only_documents"] == 4
    mock_register.assert_called_once_with()
    mock_start.assert_called_once_with(
        limit=3,
        concurrency=2,
        interval_seconds=0.5,
        include_failed=True,
    )


def test_get_local_only_batch_import_status_api_returns_service_status(monkeypatch):
    mock_status = Mock(
        return_value={
            "job_id": "job-1",
            "state": "completed",
            "total": 2,
            "processed": 2,
            "succeeded": 2,
            "failed": 0,
        }
    )
    monkeypatch.setattr(admin_api.document_service, "get_batch_import_status", mock_status)

    payload = asyncio.run(admin_api.get_local_only_batch_import_status())

    assert payload["code"] == 200
    assert payload["data"]["state"] == "completed"
    assert payload["data"]["succeeded"] == 2
    mock_status.assert_called_once_with()
