#!/usr/bin/env python3
"""
简化版测试脚本，先测试文档摘要保存功能
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.storage import (
    save_document_summary_for_classification
)


# 测试文件路径
TEST_FILES_DIR = os.path.join(os.path.dirname(__file__), 'test_date')

def get_test_files():
    """获取所有测试文件的路径"""
    test_files = []
    if os.path.exists(TEST_FILES_DIR):
        for filename in os.listdir(TEST_FILES_DIR):
            filepath = os.path.join(TEST_FILES_DIR, filename)
            if os.path.isfile(filepath):
                test_files.append(filepath)
    return test_files


def test_save_document_summary():
    """测试保存文档摘要信息"""
    print("测试保存文档摘要信息...")
    test_files = get_test_files()
    
    for filepath in test_files:
        print(f"\n测试文件: {filepath}")
        document_id, doc_info = save_document_summary_for_classification(filepath)
        if document_id and doc_info:
            print(f"成功保存文档摘要，文档ID: {document_id}")
            print(f"文件名: {doc_info['filename']}")
            print(f"文件类型: {doc_info['file_type']}")
            print(f"预览内容长度: {len(doc_info['preview_content'])} 字符")
            print(f"完整内容长度: {doc_info['full_content_length']} 字符")
        else:
            print(f"保存文档摘要失败: {filepath}")
    print("\n测试保存文档摘要信息完成\n")


def main():
    """主测试函数"""
    print("开始测试storage.py功能...\n")
    
    # 测试保存文档摘要
    test_save_document_summary()
    
    print("所有测试完成！")


if __name__ == "__main__":
    main()
