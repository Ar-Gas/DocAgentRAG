import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.document as document_api  # noqa: E402
import app.services.document_service as document_service_module  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402


def test_get_document_reader_marks_all_query_hits(monkeypatch):
    monkeypatch.setattr(
        document_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "budget-report.pdf",
            "file_type": ".pdf",
            "classification_result": "财务制度",
            "created_at_iso": "2026-03-20T10:00:00",
        },
    )
    monkeypatch.setattr(
        document_service_module,
        "get_document_content_record",
        lambda document_id: {
            "document_id": document_id,
            "full_content": "预算审批流程\n预算执行与报销约束",
            "preview_content": "预算审批流程",
            "parser_name": "pdf",
            "extraction_status": "ready",
        },
    )
    monkeypatch.setattr(
        document_service_module,
        "list_document_segments",
        lambda document_id: [
            {
                "segment_id": f"{document_id}#0",
                "segment_index": 0,
                "content": "预算审批流程",
                "page_number": 1,
                "title": "审批",
            },
            {
                "segment_id": f"{document_id}#1",
                "segment_index": 1,
                "content": "预算执行与报销约束",
                "page_number": 2,
                "title": "执行",
            },
        ],
    )

    payload = DocumentService().get_reader_payload("doc-1", query="预算")

    assert payload["document_id"] == "doc-1"
    assert payload["total_matches"] == 2
    assert payload["best_anchor"]["block_id"] == "doc-1#0"
    assert payload["blocks"][0]["matches"][0]["term"] == "预算"
    assert payload["blocks"][1]["matches"][0]["term"] == "预算"


def test_get_document_reader_uses_persisted_reader_blocks_before_legacy_segments(monkeypatch):
    monkeypatch.setattr(
        document_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "财务制度.docx",
            "file_type": ".docx",
            "classification_result": "财务制度",
            "created_at_iso": "2026-03-20T10:00:00",
        },
    )
    monkeypatch.setattr(
        document_service_module,
        "get_document_content_record",
        lambda document_id: {
            "document_id": document_id,
            "parser_name": "python-docx",
            "extraction_status": "ready",
        },
    )
    monkeypatch.setattr(
        document_service_module,
        "get_document_artifact",
        lambda document_id, artifact_type: {
            "artifact_id": "doc-1:reader_blocks",
            "payload": {
                "blocks": [
                    {
                        "block_id": "doc-1:block-v1:14",
                        "block_index": 14,
                        "block_type": "paragraph",
                        "heading_path": ["第三章 财务管理", "3.2 报销标准"],
                        "page_number": 12,
                        "text": "员工差旅报销标准如下……",
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        document_service_module,
        "list_document_segments",
        lambda document_id: [
            {"segment_id": "legacy#0", "segment_index": 0, "content": "legacy chunk"}
        ],
    )

    payload = DocumentService().get_reader_payload(
        "doc-1",
        query="报销标准",
        anchor_block_id="doc-1:block-v1:14",
    )

    assert payload["best_anchor"]["block_id"] == "doc-1:block-v1:14"
    assert payload["blocks"][0]["block_type"] == "paragraph"
    assert payload["blocks"][0]["heading_path"] == ["第三章 财务管理", "3.2 报销标准"]
    assert payload["blocks"][0]["text"] == "员工差旅报销标准如下……"


def test_document_reader_api_returns_reader_payload(monkeypatch):
    mock_get_reader_payload = Mock(
        return_value={
            "document_id": "doc-1",
            "filename": "budget-report.pdf",
            "total_matches": 1,
            "best_anchor": {"block_id": "doc-1#0", "match_index": 0},
            "blocks": [
                {
                    "block_id": "doc-1#0",
                    "block_index": 0,
                    "text": "预算审批流程",
                    "matches": [{"start": 0, "end": 2, "term": "预算"}],
                }
            ],
        }
    )
    monkeypatch.setattr(document_api.document_service, "get_reader_payload", mock_get_reader_payload)

    current_user = {"id": "user-1", "role_code": "employee"}
    body = asyncio.run(document_api.get_document_reader("doc-1", query="预算", current_user=current_user))

    assert body["code"] == 200
    assert body["data"]["document_id"] == "doc-1"
    mock_get_reader_payload.assert_called_once_with(
        "doc-1",
        query="预算",
        anchor_block_id=None,
        current_user=current_user,
    )


def test_get_document_file_quotes_unicode_filename(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        document_api.document_service,
        "get_document",
        lambda document_id, current_user=None: {
            "id": document_id,
            "filename": "指导教师名册.pdf",
            "filepath": str(pdf_path),
            "file_type": ".pdf",
        },
    )

    response = asyncio.run(
        document_api.get_document_file(
            "doc-1",
            current_user={"id": "user-1", "role_code": "employee"},
        )
    )

    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline; filename*=UTF-8''")
    assert "%E6%8C%87%E5%AF%BC%E6%95%99%E5%B8%88%E5%90%8D%E5%86%8C.pdf" in response.headers["content-disposition"]
