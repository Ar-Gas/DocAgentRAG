import os
import docx
import pandas as pd
from email import policy
from email.parser import BytesParser
import chardet



# PDF文档处理（使用PyPDF2）
def process_pdf(filepath):
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        content = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                content.append(text.strip())
        return '\n'.join(content)
    except Exception as e:
        return f"PDF处理失败: {str(e)}"



# Word文档处理
def process_word(filepath):
    try:
        doc = docx.Document(filepath)
        content = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                content.append(text)
        return '\n'.join(content)
    except Exception as e:
        return f"Word处理失败: {str(e)}"



# Excel文档处理
def process_excel(filepath):
    try:
        content = []
        # 读取所有工作表
        xls = pd.ExcelFile(filepath)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(filepath, sheet_name=sheet_name)
            content.append(f"工作表: {sheet_name}")
            # 转换为文本格式
            content.append(df.to_string(index=False))
            content.append("\n")
        return '\n'.join(content)
    except Exception as e:
        return f"Excel处理失败: {str(e)}"



# 邮件处理
def process_email(filepath):
    try:
        with open(filepath, 'rb') as f:
            msg = BytesParser(policy=policy.default).parse(f)

        content = []
        # 提取发件人
        if msg['From']:
            content.append(f"发件人: {msg['From']}")
        # 提取收件人
        if msg['To']:
            content.append(f"收件人: {msg['To']}")
        # 提取主题
        if msg['Subject']:
            content.append(f"主题: {msg['Subject']}")
        # 提取发送时间
        if msg['Date']:
            content.append(f"发送时间: {msg['Date']}")

        # 提取邮件正文
        content.append("\n邮件正文:")
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    try:
                        body = part.get_content()
                        content.append(body)
                    except Exception:
                        pass
        else:
            try:
                body = msg.get_content()
                content.append(body)
            except Exception:
                pass

        return '\n'.join(content)
    except Exception as e:
        return f"邮件处理失败: {str(e)}"



# 统一文档处理接口
def process_document(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.pdf':
        return process_pdf(filepath)
    elif ext == '.docx':
        return process_word(filepath)
    elif ext in ['.xlsx', '.xls']:
        return process_excel(filepath)
    elif ext in ['.eml', '.msg']:
        return process_email(filepath)
    else:
        # 处理其他文本文件
        try:
            with open(filepath, 'rb') as f:
                raw_data = f.read()
            encoding = chardet.detect(raw_data)['encoding']
            return raw_data.decode(encoding or 'utf-8', errors='ignore')
        except Exception as e:
            return f"文件处理失败: {str(e)}"
