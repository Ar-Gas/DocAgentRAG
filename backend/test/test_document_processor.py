import json
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
    md_file = tmp_path / "fake" / "auto" / "fake.md"
    md_file.parent.mkdir(parents=True)
    md_file.write_text("![img](x.png)\n\n正文一\n\n\n正文二", encoding="utf-8")
    captured = {}

    class FakeTempDir:
        def __enter__(self):
            return str(tmp_path)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(document_processor.tempfile, "TemporaryDirectory", lambda: FakeTempDir())
    monkeypatch.setattr(document_processor.shutil, "copy2", lambda src, dst: None)
    monkeypatch.setattr(document_processor, "_resolve_magic_pdf_command", lambda: "magic-pdf")
    monkeypatch.setattr(document_processor, "_resolve_mineru_models_dir", lambda: tmp_path / "models")
    monkeypatch.setattr(document_processor, "_ensure_mineru_model_aliases", lambda models_dir: None)

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(
        document_processor.subprocess,
        "run",
        fake_run,
    )

    success, content = document_processor.process_scanned_pdf_with_mineru("fake.pdf")

    assert success is True
    assert "正文一" in content
    assert "![img]" not in content
    config_path = Path(captured["kwargs"]["env"]["MINERU_TOOLS_CONFIG_JSON"])
    assert config_path.exists()
    config_text = config_path.read_text(encoding="utf-8")
    assert config_text.strip()
    assert "doclayout_yolo" in config_text
    assert str(tmp_path / "models") in config_text


def test_process_scanned_pdf_with_mineru_uses_virtualenv_cli_when_python_module_layout_changes(
    monkeypatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir()
    fake_python = fake_bin_dir / "python"
    fake_python.write_text("", encoding="utf-8")
    fake_magic_pdf = fake_bin_dir / "magic-pdf"
    fake_magic_pdf.write_text("#!/bin/sh\n", encoding="utf-8")

    md_file = tmp_path / "result.md"
    md_file.write_text("扫描版正文", encoding="utf-8")

    class FakeTempDir:
        def __enter__(self):
            return str(tmp_path)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(document_processor.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        document_processor,
        "sys",
        types.SimpleNamespace(executable=str(fake_python)),
        raising=False,
    )
    monkeypatch.setattr(document_processor.tempfile, "TemporaryDirectory", lambda: FakeTempDir())
    monkeypatch.setattr(document_processor.shutil, "copy2", lambda src, dst: None)
    monkeypatch.setattr(
        document_processor.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stderr=""),
    )

    success, content = document_processor.process_scanned_pdf_with_mineru("fake.pdf")

    assert success is True
    assert "扫描版正文" in content


def test_resolve_magic_pdf_command_uses_virtualenv_entrypoint_parent_without_resolving_symlink(
    monkeypatch,
    tmp_path: Path,
):
    venv_bin = tmp_path / "venv-bin"
    system_bin = tmp_path / "system-bin"
    venv_bin.mkdir()
    system_bin.mkdir()

    real_python = system_bin / "python-real"
    real_python.write_text("", encoding="utf-8")
    venv_python = venv_bin / "python"
    venv_python.symlink_to(real_python)
    venv_magic_pdf = venv_bin / "magic-pdf"
    venv_magic_pdf.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(document_processor.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        document_processor,
        "sys",
        types.SimpleNamespace(executable=str(venv_python)),
        raising=False,
    )

    assert document_processor._resolve_magic_pdf_command() == str(venv_magic_pdf)


def test_process_scanned_pdf_with_mineru_surfaces_stderr_traceback_when_cli_returns_zero(
    monkeypatch,
    tmp_path: Path,
):
    class FakeTempDir:
        def __enter__(self):
            return str(tmp_path)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(document_processor.tempfile, "TemporaryDirectory", lambda: FakeTempDir())
    monkeypatch.setattr(document_processor.shutil, "copy2", lambda src, dst: None)
    monkeypatch.setattr(document_processor, "_resolve_magic_pdf_command", lambda: "magic-pdf")
    monkeypatch.setattr(
        document_processor.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(
            returncode=0,
            stderr="Traceback (most recent call last):\npymupdf.EmptyFileError: Cannot open empty stream.\n",
            stdout="",
        ),
    )

    success, content = document_processor.process_scanned_pdf_with_mineru("fake.pdf")

    assert success is False
    assert "Cannot open empty stream" in content


def test_write_mineru_runtime_config_creates_ocr_detector_alias_when_only_v5_exists(tmp_path: Path, monkeypatch):
    models_dir = tmp_path / "modelscope-cache" / "opendatalab" / "PDF-Extract-Kit-1.0" / "models"
    ocr_dir = models_dir / "OCR" / "paddleocr_torch"
    ocr_dir.mkdir(parents=True)
    (ocr_dir / "ch_PP-OCRv5_det_infer.pth").write_text("weights", encoding="utf-8")

    monkeypatch.setattr(document_processor, "_resolve_mineru_models_dir", lambda: models_dir)

    config_path = document_processor._write_mineru_runtime_config(tmp_path)

    alias = ocr_dir / "ch_PP-OCRv3_det_infer.pth"
    assert alias.exists()
    assert json.loads(config_path.read_text(encoding="utf-8"))["models-dir"] == str(models_dir)


def test_write_mineru_runtime_config_includes_layoutreader_dir_when_available(tmp_path: Path, monkeypatch):
    models_dir = tmp_path / "models"
    layoutreader_dir = tmp_path / "layoutreader"
    models_dir.mkdir()
    layoutreader_dir.mkdir()

    monkeypatch.setattr(document_processor, "_resolve_mineru_models_dir", lambda: models_dir)
    monkeypatch.setattr(
        document_processor,
        "_resolve_layoutreader_model_dir",
        lambda: layoutreader_dir,
        raising=False,
    )

    config_path = document_processor._write_mineru_runtime_config(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config["layoutreader-model-dir"] == str(layoutreader_dir)


def test_process_scanned_pdf_with_mineru_surfaces_stderr_when_output_missing(
    monkeypatch,
    tmp_path: Path,
):
    class FakeTempDir:
        def __enter__(self):
            return str(tmp_path)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(document_processor.tempfile, "TemporaryDirectory", lambda: FakeTempDir())
    monkeypatch.setattr(document_processor.shutil, "copy2", lambda src, dst: None)
    monkeypatch.setattr(document_processor, "_resolve_magic_pdf_command", lambda: "magic-pdf")
    monkeypatch.setattr(
        document_processor.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(
            returncode=0,
            stderr="layoutreader download failed: network timeout",
            stdout="",
        ),
    )

    success, content = document_processor.process_scanned_pdf_with_mineru("fake.pdf")

    assert success is False
    assert "layoutreader download failed" in content


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
