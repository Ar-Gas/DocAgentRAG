import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document

import scripts.backfill_block_index as backfill_module  # noqa: E402


def test_backfill_dry_run_skips_unsupported_and_missing_documents(monkeypatch, capsys, tmp_path: Path):
    readable_pdf = tmp_path / "sample.pdf"
    readable_pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        backfill_module,
        "_select_candidates",
        lambda document_id="", failed_only=False, limit=0: ["doc-xlsx", "doc-missing", "doc-ok"],
    )
    monkeypatch.setattr(
        backfill_module,
        "get_document_info",
        lambda document_id: {
            "doc-xlsx": {
                "id": "doc-xlsx",
                "file_type": ".xlsx",
                "filepath": str(tmp_path / "sample.xlsx"),
            },
            "doc-missing": {
                "id": "doc-missing",
                "file_type": ".docx",
                "filepath": str(tmp_path / "missing.docx"),
            },
            "doc-ok": {
                "id": "doc-ok",
                "file_type": ".pdf",
                "filepath": str(readable_pdf),
            },
        }[document_id],
    )

    exit_code = backfill_module.backfill(dry_run=True)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "待处理文档数: 1" in output
    assert "[SKIP] doc-xlsx" in output
    assert "[SKIP] doc-missing" in output
    assert "[DRY] doc-ok" in output


def test_backfill_only_indexes_supported_readable_documents(monkeypatch, capsys, tmp_path: Path):
    readable_docx = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph("hello")
    document.save(readable_docx)
    calls = []

    class FakeIndexingService:
        def index_document(self, document_id: str, force: bool = False):
            calls.append((document_id, force))
            return {"document_id": document_id, "block_index_status": "ready"}

    monkeypatch.setattr(
        backfill_module,
        "_select_candidates",
        lambda document_id="", failed_only=False, limit=0: ["doc-txt", "doc-ok"],
    )
    monkeypatch.setattr(
        backfill_module,
        "get_document_info",
        lambda document_id: {
            "doc-txt": {
                "id": "doc-txt",
                "file_type": ".txt",
                "filepath": str(tmp_path / "sample.txt"),
            },
            "doc-ok": {
                "id": "doc-ok",
                "file_type": ".docx",
                "filepath": str(readable_docx),
            },
        }[document_id],
    )
    monkeypatch.setattr(backfill_module, "IndexingService", FakeIndexingService)

    exit_code = backfill_module.backfill()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [("doc-ok", True)]
    assert "[SKIP] doc-txt" in output
    assert "[OK]  doc-ok" in output


def test_backfill_skips_invalid_docx_package(monkeypatch, capsys, tmp_path: Path):
    fake_docx = tmp_path / "broken.docx"
    fake_docx.write_text("<html>not a real docx</html>", encoding="utf-8")

    monkeypatch.setattr(
        backfill_module,
        "_select_candidates",
        lambda document_id="", failed_only=False, limit=0: ["doc-broken"],
    )
    monkeypatch.setattr(
        backfill_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "file_type": ".docx",
            "filepath": str(fake_docx),
        },
    )

    exit_code = backfill_module.backfill(dry_run=True)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "待处理文档数: 0" in output
    assert "[SKIP] doc-broken - invalid docx package" in output
