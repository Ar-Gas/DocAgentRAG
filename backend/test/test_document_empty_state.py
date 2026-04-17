import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.services.document_service as document_service_module  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402


def test_list_documents_returns_empty_page_when_repository_raises(monkeypatch):
    monkeypatch.setattr(
        document_service_module,
        "get_all_documents",
        lambda: (_ for _ in ()).throw(RuntimeError("sqlite unavailable")),
    )

    payload = DocumentService().list_documents(1, 20)

    assert payload == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "total_pages": 0,
    }


def test_list_documents_skips_broken_document_rows(monkeypatch):
    monkeypatch.setattr(
        document_service_module,
        "get_all_documents",
        lambda: [
            {"id": "doc-1", "filename": "正常文档.pdf"},
            {"id": "doc-2", "filename": "损坏文档.pdf"},
        ],
    )
    monkeypatch.setattr(
        DocumentService,
        "_hydrate_document",
        staticmethod(
            lambda doc_info: (
                doc_info
                if doc_info.get("id") == "doc-1"
                else (_ for _ in ()).throw(ValueError("payload mismatch"))
            )
        ),
    )

    payload = DocumentService().list_documents(1, 20)

    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 20
    assert payload["items"] == [{"id": "doc-1", "filename": "正常文档.pdf"}]
