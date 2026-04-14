import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import document_processor


def test_process_document_treats_parser_failure_strings_as_failure(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_text("broken", encoding="utf-8")

    monkeypatch.setattr(document_processor, "_check_file_validity", lambda filepath: (True, ""))
    monkeypatch.setattr(document_processor, "process_pdf", lambda filepath: "PDF处理失败: mock failure")

    success, content = document_processor.process_document(str(pdf_path))

    assert success is False
    assert content.startswith("PDF处理失败")


def test_process_document_returns_false_when_parser_reports_scan_failure(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_text("broken", encoding="utf-8")

    monkeypatch.setattr(document_processor, "_check_file_validity", lambda filepath: (True, ""))
    monkeypatch.setattr(document_processor, "process_pdf", lambda filepath: "（扫描版PDF，MinerU处理失败：mock）")

    success, content = document_processor.process_document(str(pdf_path))

    assert success is False
    assert "MinerU处理失败" in content
