import os
import sys
import types
from pathlib import Path

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import document_processor  # noqa: E402


def test_check_file_validity_and_truncate(monkeypatch, tmp_path: Path):
    test_file = tmp_path / "doc.txt"
    test_file.write_text("hello", encoding="utf-8")

    assert document_processor._check_file_validity(str(test_file)) == (True, "")
    assert document_processor._check_file_validity(str(tmp_path / "missing.txt")) == (False, "文件不存在")

    monkeypatch.setattr(document_processor, "MAX_FILE_SIZE", 2)
    assert document_processor._check_file_validity(str(test_file))[0] is False

    monkeypatch.setattr(document_processor, "MAX_TEXT_LENGTH", 5)
    assert document_processor._truncate_text("123456").endswith("（文本过长，已截断）")


def test_is_scanned_pdf_uses_pdf_reader(monkeypatch):
    dense_page = types.SimpleNamespace(extract_text=lambda: "文本" * 100)
    sparse_page = types.SimpleNamespace(extract_text=lambda: "")

    monkeypatch.setattr(document_processor, "PdfReader", lambda filepath: types.SimpleNamespace(pages=[dense_page]))
    assert document_processor._is_scanned_pdf("fake.pdf") is False

    monkeypatch.setattr(document_processor, "PdfReader", lambda filepath: types.SimpleNamespace(pages=[sparse_page]))
    assert document_processor._is_scanned_pdf("fake.pdf") is True


def test_process_scanned_pdf_with_mineru_success(monkeypatch, tmp_path: Path):
    fake_magic_pdf = types.ModuleType("magic_pdf")
    fake_magic_pdf_cli = types.ModuleType("magic_pdf.cli")
    fake_magic_pdf_cli.magic_pdf = object()
    fake_magic_pdf.cli = fake_magic_pdf_cli

    sys.modules["magic_pdf"] = fake_magic_pdf
    sys.modules["magic_pdf.cli"] = fake_magic_pdf_cli

    md_file = tmp_path / "result.md"
    md_file.write_text("![img](x.png)\n\n正文一\n\n\n正文二", encoding="utf-8")

    class FakeTempDir:
        def __enter__(self):
            return str(tmp_path)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(document_processor.tempfile, "TemporaryDirectory", lambda: FakeTempDir())
    monkeypatch.setattr(document_processor.shutil, "copy2", lambda src, dst: None)
    monkeypatch.setattr(
        document_processor.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stderr=""),
    )

    success, content = document_processor.process_scanned_pdf_with_mineru("fake.pdf")

    assert success is True
    assert "正文一" in content
    assert "![img]" not in content

    sys.modules.pop("magic_pdf", None)
    sys.modules.pop("magic_pdf.cli", None)


def test_process_pdf_uses_text_or_ocr(monkeypatch):
    rich_page = types.SimpleNamespace(extract_text=lambda: "这是第1页内容" * 30)
    empty_page = types.SimpleNamespace(extract_text=lambda: "")

    monkeypatch.setattr(document_processor, "PdfReader", lambda filepath: types.SimpleNamespace(pages=[rich_page]))
    content = document_processor.process_pdf("fake.pdf")
    assert "第 1 页" in content

    monkeypatch.setattr(document_processor, "PdfReader", lambda filepath: types.SimpleNamespace(pages=[empty_page]))
    monkeypatch.setattr(document_processor, "process_scanned_pdf_with_mineru", lambda filepath: (True, "OCR 内容"))
    assert document_processor.process_pdf("fake.pdf") == "OCR 内容"


def test_process_word_extracts_paragraphs_and_tables(monkeypatch):
    paragraph1 = types.SimpleNamespace(text="第一段")
    paragraph2 = types.SimpleNamespace(text="第二段")
    row = types.SimpleNamespace(cells=[types.SimpleNamespace(text="单元格1"), types.SimpleNamespace(text="单元格2")])
    table = types.SimpleNamespace(rows=[row])
    fake_doc = types.SimpleNamespace(paragraphs=[paragraph1, paragraph2], tables=[table])

    monkeypatch.setattr(document_processor, "docx", types.SimpleNamespace(Document=lambda filepath: fake_doc))
    content = document_processor.process_word("fake.docx")

    assert "第一段" in content
    assert "第二段" in content
    assert "单元格1 | 单元格2" in content


def test_process_excel_extracts_sheet_text(monkeypatch):
    df = pd.DataFrame({"列1": ["值1", "值2"], "列2": ["值3", "值4"]})
    fake_pd = types.SimpleNamespace(
        ExcelFile=lambda filepath: types.SimpleNamespace(sheet_names=["Sheet1", "Sheet2"]),
        read_excel=lambda filepath, sheet_name: df,
    )

    monkeypatch.setattr(document_processor, "pd", fake_pd)
    content = document_processor.process_excel("fake.xlsx")

    assert "工作表: Sheet1" in content
    assert "工作表: Sheet2" in content
    assert "值1" in content


def test_process_ppt_extracts_text_and_table(monkeypatch):
    row = types.SimpleNamespace(cells=[types.SimpleNamespace(text="表格内容")])
    table = types.SimpleNamespace(rows=[row])
    text_shape = types.SimpleNamespace(text="文本框内容", has_table=False)
    table_shape = types.SimpleNamespace(text="", has_table=True, table=table)
    slide = types.SimpleNamespace(shapes=[text_shape, table_shape])
    fake_prs = types.SimpleNamespace(slides=[slide])

    monkeypatch.setattr(document_processor, "Presentation", lambda filepath: fake_prs)
    content = document_processor.process_ppt("fake.pptx")

    assert "第 1 页" in content
    assert "文本框内容" in content
    assert "表格内容" in content


def test_process_email_eml_returns_headers_and_body(tmp_path: Path):
    email_file = tmp_path / "test.eml"
    email_file.write_bytes(
        b"From: sender@example.com\nTo: recipient@example.com\nSubject: Test Email\nDate: Mon, 01 Jan 2026 12:00:00 +0000\n\nThis is the email body\n"
    )

    content = document_processor.process_email(str(email_file))

    assert "发件人: sender@example.com" in content
    assert "收件人: recipient@example.com" in content
    assert "主题: Test Email" in content
    assert "This is the email body" in content


def test_process_document_dispatch_and_failure(monkeypatch, tmp_path: Path):
    text_file = tmp_path / "plain.txt"
    text_file.write_text("文本内容", encoding="utf-8")

    success, content = document_processor.process_document(str(text_file))
    assert success is True
    assert "文本内容" in content

    pdf_file = tmp_path / "broken.pdf"
    pdf_file.write_text("broken", encoding="utf-8")
    monkeypatch.setattr(document_processor, "process_pdf", lambda filepath: "PDF处理失败: mock")
    success, content = document_processor.process_document(str(pdf_file))
    assert success is False
    assert content.startswith("PDF处理失败")
