#!/usr/bin/env python3
import unittest
from unittest import mock
import tempfile
import shutil
import os
import sys
from pathlib import Path
from io import BytesIO

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.document_processor import (
    _check_file_validity,
    _truncate_text,
    _is_scanned_pdf,
    process_scanned_pdf_with_mineru,
    process_pdf,
    process_word,
    process_excel,
    process_ppt,
    process_email,
    process_document,
    MAX_FILE_SIZE,
    MAX_TEXT_LENGTH
)

class TestDocumentProcessor(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("测试内容")
    
    def tearDown(self):
        # Clean up temporary directory
        shutil.rmtree(self.temp_dir)
    
    # ===================== 测试工具函数 =====================
    def test_check_file_validity_exists(self):
        """测试文件存在且大小合法"""
        is_valid, error_msg = _check_file_validity(self.test_file)
        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")
    
    def test_check_file_validity_not_exists(self):
        """测试文件不存在"""
        non_existent_file = os.path.join(self.temp_dir, "non_existent.txt")
        is_valid, error_msg = _check_file_validity(non_existent_file)
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "文件不存在")
    
    def test_check_file_validity_too_large(self):
        """测试文件过大"""
        # Create a large file (just over MAX_FILE_SIZE)
        large_file = os.path.join(self.temp_dir, "large.txt")
        with open(large_file, 'wb') as f:
            f.write(b'x' * (MAX_FILE_SIZE + 1))
        
        is_valid, error_msg = _check_file_validity(large_file)
        self.assertFalse(is_valid)
        self.assertIn("文件过大", error_msg)
    
    def test_truncate_text_normal(self):
        """测试正常文本不截断"""
        text = "这是一段正常长度的文本"
        truncated = _truncate_text(text)
        self.assertEqual(truncated, text)
    
    def test_truncate_text_too_long(self):
        """测试超长文本截断"""
        text = "x" * (MAX_TEXT_LENGTH + 100)
        truncated = _truncate_text(text)
        self.assertEqual(len(truncated), MAX_TEXT_LENGTH + len("\n（文本过长，已截断）"))
        self.assertIn("（文本过长，已截断）", truncated)
    
    @mock.patch('utils.document_processor.PdfReader')
    def test_is_scanned_pdf_normal(self, mock_pdf_reader):
        """测试正常PDF（非扫描版）"""
        # Mock a normal PDF with text
        mock_reader = mock.MagicMock()
        mock_pdf_reader.return_value = mock_reader
        mock_page = mock.MagicMock()
        mock_page.extract_text.return_value = "这是正常PDF的文本内容" * 10
        mock_reader.pages = [mock_page] * 5
        
        is_scanned = _is_scanned_pdf("test.pdf")
        self.assertFalse(is_scanned)
    
    @mock.patch('utils.document_processor.PdfReader')
    def test_is_scanned_pdf_scanned(self, mock_pdf_reader):
        """测试扫描版PDF"""
        # Mock a scanned PDF with no text
        mock_reader = mock.MagicMock()
        mock_pdf_reader.return_value = mock_reader
        mock_page = mock.MagicMock()
        mock_page.extract_text.return_value = ""
        mock_reader.pages = [mock_page] * 5
        
        is_scanned = _is_scanned_pdf("test.pdf")
        self.assertTrue(is_scanned)
    
    @mock.patch('utils.document_processor.PdfReader')
    def test_is_scanned_pdf_exception(self, mock_pdf_reader):
        """测试检测PDF类型时发生异常"""
        mock_pdf_reader.side_effect = Exception("Test exception")
        is_scanned = _is_scanned_pdf("test.pdf")
        self.assertTrue(is_scanned)  # 默认按扫描版处理
    
    # ===================== 测试 process_scanned_pdf_with_mineru =====================
    @mock.patch('utils.document_processor.subprocess.run')
    @mock.patch('utils.document_processor.shutil.copy2')
    @mock.patch('utils.document_processor.tempfile.TemporaryDirectory')
    def test_process_scanned_pdf_with_mineru_normal(self, mock_temp_dir, mock_copy, mock_subprocess):
        """测试正常使用MinerU处理扫描版PDF"""
        # Mock temp directory
        mock_temp_path = Path(self.temp_dir)
        mock_temp_dir.return_value.__enter__.return_value = str(mock_temp_path)
        
        # Mock subprocess run (MinerU success)
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result
        
        # Create a mock MD file in temp dir
        mock_md_file = mock_temp_path / "test.md"
        with open(mock_md_file, 'w', encoding='utf-8') as f:
            f.write("![图片](test.png)\n\n这是MinerU提取的文本\n\n\n\n这是另一段文本")
        
        # Test
        success, content = process_scanned_pdf_with_mineru("test.pdf")
        
        # Verify
        self.assertTrue(success)
        self.assertNotIn("![图片](test.png)", content)  # 图片应被去除
        self.assertNotIn("\n\n\n\n", content)  # 多余空行应被去除
        self.assertIn("这是MinerU提取的文本", content)
    
    @mock.patch('utils.document_processor.subprocess.run')
    @mock.patch('utils.document_processor.shutil.copy2')
    @mock.patch('utils.document_processor.tempfile.TemporaryDirectory')
    def test_process_scanned_pdf_with_mineru_failed(self, mock_temp_dir, mock_copy, mock_subprocess):
        """测试MinerU处理失败"""
        # Mock temp directory
        mock_temp_path = Path(self.temp_dir)
        mock_temp_dir.return_value.__enter__.return_value = str(mock_temp_path)
        
        # Mock subprocess run (MinerU failed)
        mock_result = mock.MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "MinerU error message"
        mock_subprocess.return_value = mock_result
        
        # Test
        success, content = process_scanned_pdf_with_mineru("test.pdf")
        
        # Verify
        self.assertFalse(success)
        self.assertIn("MinerU处理失败", content)
    
    @mock.patch('utils.document_processor.subprocess.run')
    @mock.patch('utils.document_processor.shutil.copy2')
    @mock.patch('utils.document_processor.tempfile.TemporaryDirectory')
    def test_process_scanned_pdf_with_mineru_timeout(self, mock_temp_dir, mock_copy, mock_subprocess):
        """测试MinerU处理超时"""
        # Mock temp directory
        mock_temp_path = Path(self.temp_dir)
        mock_temp_dir.return_value.__enter__.return_value = str(mock_temp_path)
        
        # Mock subprocess run (timeout)
        import subprocess
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="magic-pdf", timeout=600)
        
        # Test
        success, content = process_scanned_pdf_with_mineru("test.pdf")
        
        # Verify
        self.assertFalse(success)
        self.assertIn("MinerU处理超时", content)
    
    def test_process_scanned_pdf_with_mineru_not_installed(self):
        """测试MinerU未安装"""
        # Mock import error
        with mock.patch.dict('sys.modules', {'magic_pdf': None}):
            with mock.patch('utils.document_processor.logger') as mock_logger:
                success, content = process_scanned_pdf_with_mineru("test.pdf")
                self.assertFalse(success)
                self.assertIn("MinerU未安装", content)
    
    # ===================== 测试 process_pdf =====================
    @mock.patch('utils.document_processor._is_scanned_pdf')
    @mock.patch('utils.document_processor.PdfReader')
    def test_process_pdf_normal(self, mock_pdf_reader, mock_is_scanned):
        """测试正常PDF处理"""
        # Mock not scanned
        mock_is_scanned.return_value = False
        
        # Mock PDF with text
        mock_reader = mock.MagicMock()
        mock_pdf_reader.return_value = mock_reader
        mock_page = mock.MagicMock()
        mock_page.extract_text.return_value = "这是第1页的内容"
        mock_reader.pages = [mock_page] * 5
        
        # Test
        content = process_pdf("test.pdf")
        
        # Verify
        self.assertIn("第 1 页", content)
        self.assertIn("这是第1页的内容", content)
    
    @mock.patch('utils.document_processor.process_scanned_pdf_with_mineru')
    @mock.patch('utils.document_processor._is_scanned_pdf')
    @mock.patch('utils.document_processor.PdfReader')
    def test_process_pdf_scanned_success(self, mock_pdf_reader, mock_is_scanned, mock_mineru):
        """测试扫描版PDF处理成功"""
        # Mock scanned
        mock_is_scanned.return_value = True
        
        # Mock PDF with no text
        mock_reader = mock.MagicMock()
        mock_pdf_reader.return_value = mock_reader
        mock_page = mock.MagicMock()
        mock_page.extract_text.return_value = ""
        mock_reader.pages = [mock_page] * 5
        
        # Mock MinerU success
        mock_mineru.return_value = (True, "这是MinerU OCR提取的文本")
        
        # Test
        content = process_pdf("test.pdf")
        
        # Verify
        self.assertEqual(content, "这是MinerU OCR提取的文本")
    
    @mock.patch('utils.document_processor.process_scanned_pdf_with_mineru')
    @mock.patch('utils.document_processor._is_scanned_pdf')
    @mock.patch('utils.document_processor.PdfReader')
    def test_process_pdf_scanned_failed(self, mock_pdf_reader, mock_is_scanned, mock_mineru):
        """测试扫描版PDF处理失败"""
        # Mock scanned
        mock_is_scanned.return_value = True
        
        # Mock PDF with no text
        mock_reader = mock.MagicMock()
        mock_pdf_reader.return_value = mock_reader
        mock_page = mock.MagicMock()
        mock_page.extract_text.return_value = ""
        mock_reader.pages = [mock_page] * 5
        
        # Mock MinerU failed
        mock_mineru.return_value = (False, "MinerU错误")
        
        # Test
        content = process_pdf("test.pdf")
        
        # Verify
        self.assertIn("扫描版PDF，MinerU处理失败", content)
    
    @mock.patch('utils.document_processor.PdfReader')
    def test_process_pdf_exception(self, mock_pdf_reader):
        """测试PDF处理时发生异常"""
        mock_pdf_reader.side_effect = Exception("Test exception")
        content = process_pdf("test.pdf")
        self.assertIn("PDF处理失败", content)
    
    # ===================== 测试 process_word =====================
    @mock.patch('utils.document_processor.docx.Document')
    def test_process_word_normal(self, mock_doc):
        """测试正常Word处理"""
        # Mock Word document
        mock_document = mock.MagicMock()
        mock_doc.return_value = mock_document
        
        # Mock paragraphs
        mock_para1 = mock.MagicMock()
        mock_para1.text = "这是第一段"
        mock_para2 = mock.MagicMock()
        mock_para2.text = "这是第二段"
        mock_document.paragraphs = [mock_para1, mock_para2]
        
        # Mock tables
        mock_table = mock.MagicMock()
        mock_row = mock.MagicMock()
        mock_cell1 = mock.MagicMock()
        mock_cell1.text = "单元格1"
        mock_cell2 = mock.MagicMock()
        mock_cell2.text = "单元格2"
        mock_row.cells = [mock_cell1, mock_cell2]
        mock_table.rows = [mock_row]
        mock_document.tables = [mock_table]
        
        # Test
        content = process_word("test.docx")
        
        # Verify
        self.assertIn("这是第一段", content)
        self.assertIn("这是第二段", content)
        self.assertIn("表格内容", content)
        self.assertIn("单元格1 | 单元格2", content)
    
    @mock.patch('utils.document_processor.docx.Document')
    def test_process_word_exception(self, mock_doc):
        """测试Word处理时发生异常"""
        mock_doc.side_effect = Exception("Test exception")
        content = process_word("test.docx")
        self.assertIn("Word处理失败", content)
    
    # ===================== 测试 process_excel =====================
    @mock.patch('utils.document_processor.pd.ExcelFile')
    @mock.patch('utils.document_processor.pd.read_excel')
    def test_process_excel_normal(self, mock_read_excel, mock_excel_file):
        """测试正常Excel处理"""
        # Mock Excel file
        mock_xls = mock.MagicMock()
        mock_excel_file.return_value = mock_xls
        mock_xls.sheet_names = ["Sheet1", "Sheet2"]
        
        # Mock DataFrame
        import pandas as pd
        mock_df = pd.DataFrame({
            '列1': ['值1', '值2'],
            '列2': ['值3', '值4']
        })
        mock_read_excel.return_value = mock_df
        
        # Test
        content = process_excel("test.xlsx")
        
        # Verify
        self.assertIn("工作表: Sheet1", content)
        self.assertIn("工作表: Sheet2", content)
        self.assertIn("列1", content)
        self.assertIn("值1", content)
    
    @mock.patch('utils.document_processor.pd.ExcelFile')
    def test_process_excel_exception(self, mock_excel_file):
        """测试Excel处理时发生异常"""
        mock_excel_file.side_effect = Exception("Test exception")
        content = process_excel("test.xlsx")
        self.assertIn("Excel处理失败", content)
    
    # ===================== 测试 process_ppt =====================
    @mock.patch('utils.document_processor.Presentation')
    def test_process_ppt_normal(self, mock_presentation):
        """测试正常PPT处理"""
        # Mock PPT
        mock_prs = mock.MagicMock()
        mock_presentation.return_value = mock_prs
        
        # Mock slide
        mock_slide = mock.MagicMock()
        # Mock text shape
        mock_shape = mock.MagicMock()
        mock_shape.text = "这是文本框内容"
        mock_slide.shapes = [mock_shape]
        # Mock table
        mock_table = mock.MagicMock()
        mock_row = mock.MagicMock()
        mock_cell = mock.MagicMock()
        mock_cell.text = "表格内容"
        mock_row.cells = [mock_cell]
        mock_table.rows = [mock_row]
        mock_slide.shapes.tables = [mock_table]
        
        mock_prs.slides = [mock_slide]
        
        # Test
        content = process_ppt("test.pptx")
        
        # Verify
        self.assertIn("第 1 页", content)
        self.assertIn("这是文本框内容", content)
        self.assertIn("表格内容", content)
    
    @mock.patch('utils.document_processor.Presentation')
    def test_process_ppt_exception(self, mock_presentation):
        """测试PPT处理时发生异常"""
        mock_presentation.side_effect = Exception("Test exception")
        content = process_ppt("test.pptx")
        self.assertIn("PPT处理失败", content)
    
    # ===================== 测试 process_email =====================
    def test_process_email_normal(self):
        """测试正常邮件处理"""
        # Create a test email file (English content to avoid non-ASCII warning)
        email_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 01 Jan 2026 12:00:00 +0000

This is the email body
"""
        email_file = os.path.join(self.temp_dir, "test.eml")
        with open(email_file, 'wb') as f:
            f.write(email_content)
        
        # Test
        content = process_email(email_file)
        
        # Verify
        self.assertIn("From: sender@example.com", content)
        self.assertIn("To: recipient@example.com", content)
        self.assertIn("Subject: Test Email", content)
        self.assertIn("This is the email body", content)
    
    def test_process_document_text(self):
        """测试其他文本文件处理"""
        # Create a test text file (English content to avoid non-ASCII warning)
        test_text = os.path.join(self.temp_dir, "test.txt")
        with open(test_text, 'w', encoding='utf-8') as f:
            f.write("This is the text file content")
        
        success, content = process_document(test_text)
        self.assertTrue(success)
        self.assertIn("This is the text file content", content)
    
    # ===================== 测试 process_document =====================
    def test_process_document_invalid_file(self):
        """测试文件校验失败"""
        # Non-existent file
        success, content = process_document("non_existent.txt")
        self.assertFalse(success)
        self.assertEqual(content, "文件不存在")
    
    @mock.patch('utils.document_processor.process_pdf')
    def test_process_document_pdf(self, mock_process_pdf):
        """测试PDF文件处理"""
        mock_process_pdf.return_value = "PDF内容"
        
        # Create a test PDF file
        test_pdf = os.path.join(self.temp_dir, "test.pdf")
        with open(test_pdf, 'w') as f:
            f.write("mock pdf")
        
        success, content = process_document(test_pdf)
        self.assertTrue(success)
        self.assertEqual(content, "PDF内容")
        mock_process_pdf.assert_called_once_with(test_pdf)
    
    @mock.patch('utils.document_processor.process_word')
    def test_process_document_word(self, mock_process_word):
        """测试Word文件处理"""
        mock_process_word.return_value = "Word内容"
        
        # Create a test Word file
        test_word = os.path.join(self.temp_dir, "test.docx")
        with open(test_word, 'w') as f:
            f.write("mock word")
        
        success, content = process_document(test_word)
        self.assertTrue(success)
        self.assertEqual(content, "Word内容")
    
    @mock.patch('utils.document_processor.process_excel')
    def test_process_document_excel(self, mock_process_excel):
        """测试Excel文件处理"""
        mock_process_excel.return_value = "Excel内容"
        
        # Create a test Excel file
        test_excel = os.path.join(self.temp_dir, "test.xlsx")
        with open(test_excel, 'w') as f:
            f.write("mock excel")
        
        success, content = process_document(test_excel)
        self.assertTrue(success)
        self.assertEqual(content, "Excel内容")
    
    @mock.patch('utils.document_processor.process_ppt')
    def test_process_document_ppt(self, mock_process_ppt):
        """测试PPT文件处理"""
        mock_process_ppt.return_value = "PPT内容"
        
        # Create a test PPT file
        test_ppt = os.path.join(self.temp_dir, "test.pptx")
        with open(test_ppt, 'w') as f:
            f.write("mock ppt")
        
        success, content = process_document(test_ppt)
        self.assertTrue(success)
        self.assertEqual(content, "PPT内容")
    
    @mock.patch('utils.document_processor.process_email')
    def test_process_document_email(self, mock_process_email):
        """测试邮件文件处理"""
        mock_process_email.return_value = "邮件内容"
        
        # Create a test email file
        test_email = os.path.join(self.temp_dir, "test.eml")
        with open(test_email, 'w') as f:
            f.write("mock email")
        
        success, content = process_document(test_email)
        self.assertTrue(success)
        self.assertEqual(content, "邮件内容")
    
    def test_process_document_text(self):
        """测试其他文本文件处理"""
        # Create a test text file
        test_text = os.path.join(self.temp_dir, "test.txt")
        with open(test_text, 'w', encoding='utf-8') as f:
            f.write("这是文本文件内容")
        
        success, content = process_document(test_text)
        self.assertTrue(success)
        self.assertIn("这是文本文件内容", content)
    
    @mock.patch('utils.document_processor.process_pdf')
    def test_process_document_failed(self, mock_process_pdf):
        """测试文档处理失败"""
        mock_process_pdf.return_value = "PDF处理失败: Test error"
        
        # Create a test PDF file
        test_pdf = os.path.join(self.temp_dir, "test.pdf")
        with open(test_pdf, 'w') as f:
            f.write("mock pdf")
        
        success, content = process_document(test_pdf)
        self.assertFalse(success)
        self.assertIn("PDF处理失败", content)

if __name__ == '__main__':
    unittest.main()