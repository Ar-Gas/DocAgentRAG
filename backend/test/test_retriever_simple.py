#!/usr/bin/env python3
"""
简单测试向量检索功能
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.retriever import (
    search_documents,
    batch_search_documents,
    get_document_by_id,
    get_document_stats
)


def test_retriever_functions():
    """测试retriever的基本函数"""
    print("开始测试retriever基本功能...\n")
    
    # 测试search_documents函数
    print("1. 测试search_documents函数...")
    try:
        query = "测试"
        results = search_documents(query, limit=5)
        print(f"   搜索查询: '{query}'")
        print(f"   返回结果类型: {type(results)}")
        print(f"   返回结果数量: {len(results)}")
        if results and isinstance(results, list):
            print("   ✓ 搜索功能正常")
        else:
            print("   ⚠ 搜索结果为空或格式不正确")
    except Exception as e:
        print(f"   ✗ 搜索功能异常: {str(e)}")
    
    # 测试batch_search_documents函数
    print("\n2. 测试batch_search_documents函数...")
    try:
        queries = ["测试", "数据", "文档"]
        results = batch_search_documents(queries, limit=3)
        print(f"   查询数量: {len(queries)}")
        print(f"   返回结果类型: {type(results)}")
        print(f"   返回结果数量: {len(results)}")
        if results and isinstance(results, list) and len(results) == len(queries):
            print("   ✓ 批量搜索功能正常")
        else:
            print("   ⚠ 批量搜索结果为空或格式不正确")
    except Exception as e:
        print(f"   ✗ 批量搜索功能异常: {str(e)}")
    
    # 测试get_document_by_id函数
    print("\n3. 测试get_document_by_id函数...")
    try:
        test_doc_id = "test_document_id"
        result = get_document_by_id(test_doc_id)
        print(f"   测试文档ID: {test_doc_id}")
        print(f"   返回结果类型: {type(result)}")
        if result is None or isinstance(result, dict):
            print("   ✓ 根据ID获取文档功能正常")
        else:
            print("   ⚠ 根据ID获取文档结果格式不正确")
    except Exception as e:
        print(f"   ✗ 根据ID获取文档功能异常: {str(e)}")
    
    # 测试get_document_stats函数
    print("\n4. 测试get_document_stats函数...")
    try:
        stats = get_document_stats()
        print(f"   返回结果类型: {type(stats)}")
        if isinstance(stats, dict):
            print(f"   总chunks数量: {stats.get('total_chunks', 0)}")
            print(f"   文件类型统计: {stats.get('file_types', {})}")
            print("   ✓ 获取统计信息功能正常")
        else:
            print("   ⚠ 获取统计信息结果格式不正确")
    except Exception as e:
        print(f"   ✗ 获取统计信息功能异常: {str(e)}")
    
    print("\n所有测试完成！")


def main():
    """主测试函数"""
    test_retriever_functions()


if __name__ == "__main__":
    main()
