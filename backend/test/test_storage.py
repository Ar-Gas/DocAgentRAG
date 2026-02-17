#!/usr/bin/env python3
"""
测试storage.py中的功能，使用真实的测试文件
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.storage import (
    save_document_summary_for_classification,
    save_document_to_chroma,
    retrieve_from_chroma
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


def test_save_document_to_chroma():
    """测试保存文档到Chroma"""
    print("测试保存文档到Chroma...")
    test_files = get_test_files()
    
    for filepath in test_files:
        print(f"\n测试文件: {filepath}")
        # 先保存摘要获取document_id
        document_id, _ = save_document_summary_for_classification(filepath)
        if document_id:
            success = save_document_to_chroma(filepath, document_id)
            if success:
                print(f"成功保存文档到Chroma: {filepath}")
            else:
                print(f"保存文档到Chroma失败: {filepath}")
        else:
            print(f"获取document_id失败: {filepath}")
    print("\n测试保存文档到Chroma完成\n")


def test_retrieve_from_chroma():
    """测试从Chroma检索文档"""
    print("测试从Chroma检索文档...")
    
    # 测试不同类型的查询
    test_queries = [
        "测试",
        "sample",
        "document",
        "data",
        "email"
    ]
    
    for query in test_queries:
        print(f"\n查询: {query}")
        results = retrieve_from_chroma(query, n_results=3)
        if results:
            print(f"检索结果数量: {len(results.get('documents', []))}")
            if 'documents' in results:
                for i, doc in enumerate(results['documents'][0]):
                    print(f"结果 {i+1}: {doc[:100]}...")
                    if 'metadatas' in results and results['metadatas']:
                        metadata = results['metadatas'][0][i]
                        print(f"  来源文件: {metadata.get('filename', '未知')}")
        else:
            print("未找到检索结果")
    print("\n测试从Chroma检索文档完成\n")


def main():
    """主测试函数"""
    print("开始测试storage.py功能...\n")
    
    # 测试保存文档摘要
    test_save_document_summary()
    
    # 测试保存文档到Chroma
    test_save_document_to_chroma()
    
    # 测试从Chroma检索文档
    test_retrieve_from_chroma()
    
    print("所有测试完成！")


if __name__ == "__main__":
    main()
