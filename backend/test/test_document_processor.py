import os
import sys
import tempfile

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.document_processor import process_pdf, process_word, process_excel, process_email, process_document

# 创建测试文件
print("开始测试文档处理器...")

# 测试PDF处理
try:
    # 创建一个简单的PDF文件进行测试
    # 注意：这里我们只是测试函数是否能正常运行，实际PDF内容提取需要真实的PDF文件
    test_pdf_path = "test/test_date/sample.pdf"
    if os.path.exists(test_pdf_path):
        pdf_content = process_pdf(test_pdf_path)
        print(f"PDF处理成功: {pdf_content[:100]}...")
    else:
        print("PDF测试文件不存在，跳过PDF测试")
except Exception as e:
    print(f"PDF测试失败: {str(e)}")

# 测试Word处理
try:
    # 创建一个简单的Word文件进行测试
    test_word_path = "test/test_date/sample.docx"
    if os.path.exists(test_word_path):
        word_content = process_word(test_word_path)
        print(f"Word处理成功: {word_content[:100]}...")
    else:
        print("Word测试文件不存在，跳过Word测试")
except Exception as e:
    print(f"Word测试失败: {str(e)}")

# 测试Excel处理
try:
    # 创建一个简单的Excel文件进行测试
    test_excel_path = "test/test_date/sample.xlsx"
    if os.path.exists(test_excel_path):
        excel_content = process_excel(test_excel_path)
        print(f"Excel处理成功: {excel_content[:100]}...")
    else:
        print("Excel测试文件不存在，跳过Excel测试")
except Exception as e:
    print(f"Excel测试失败: {str(e)}")

# 测试统一文档处理接口
try:
    # 测试文本文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("测试文本文件内容")
        test_txt_path = f.name
    
    txt_content = process_document(test_txt_path)
    print(f"文本文件处理成功: {txt_content}")
    os.unlink(test_txt_path)
except Exception as e:
    print(f"文本文件测试失败: {str(e)}")

print("文档处理器测试完成！")
