#!/usr/bin/env python3
"""
测试向量检索功能
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
from utils.storage import (
    save_document_summary_for_classification,
    save_document_to_chroma
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


def prepare_test_data():
    """准备测试数据"""
    print("准备测试数据...")
    test_files = get_test_files()
    
    # 先测试一个较小的文件
    small_file = None
    for filepath in test_files:
        if os.path.getsize(filepath) < 10000:  # 选择小于10KB的文件
            small_file = filepath
            break
    
    if small_file:
        print(f"测试文件: {small_file}")
        # 先保存摘要获取document_id
        document_id, _ = save_document_summary_for_classification(small_file)
        if document_id:
            print(f"获取document_id成功: {document_id}")
            print("正在保存到Chroma...")
            success = save_document_to_chroma(small_file, document_id)
            if success:
                print(f"成功保存文档到Chroma: {small_file}")
                return document_id
            else:
                print(f"保存文档到Chroma失败: {small_file}")
        else:
            print(f"获取document_id失败: {small_file}")
    else:
        print("未找到合适的测试文件")
    return None


def test_search_documents():
    """测试搜索文档功能"""
    print("\n测试搜索文档功能...")
    
    # 测试基本搜索
    query = "测试"
    results = search_documents(query, limit=5)
    
    print(f"搜索查询: '{query}'")
    print(f"搜索结果数量: {len(results)}")
    
    if results:
        print("\n搜索结果:")
        for i, result in enumerate(results[:3]):  # 只显示前3个结果
            print(f"\n结果 {i+1}:")
            print(f"  文档ID: {result['document_id']}")
            print(f"  文件名: {result['filename']}")
            print(f"  相似度: {result['similarity']:.4f}")
            print(f"  内容片段: {result['content_snippet'][:100]}...")
    else:
        print("无搜索结果")
    print("\n测试搜索文档功能完成")


def test_batch_search_documents():
    """测试批量搜索文档功能"""
    print("\n测试批量搜索文档功能...")
    
    # 测试批量搜索
    queries = ["测试", "数据", "文档"]
    results = batch_search_documents(queries, limit=3)
    
    for i, (query, query_results) in enumerate(zip(queries, results)):
        print(f"\n查询 {i+1}: '{query}'")
        print(f"结果数量: {len(query_results)}")
        if query_results:
            print(f"最高相似度: {query_results[0]['similarity']:.4f}")
    print("\n测试批量搜索文档功能完成")


def test_get_document_by_id(document_id):
    """测试根据文档ID获取文档信息"""
    print("\n测试根据文档ID获取文档信息...")
    
    if document_id:
        result = get_document_by_id(document_id)
        if result:
            print(f"文档ID: {document_id}")
            print(f" chunks数量: {len(result['chunks'])}")
            print(f" metadatas数量: {len(result['metadatas'])}")
            print(f" ids数量: {len(result['ids'])}")
            if result['chunks']:
                print(f"第一个chunk内容: {result['chunks'][0][:100]}...")
        else:
            print(f"未找到文档: {document_id}")
    else:
        print("无文档ID，跳过测试")
    print("\n测试根据文档ID获取文档信息完成")


def test_get_document_stats():
    """测试获取文档统计信息"""
    print("\n测试获取文档统计信息...")
    
    stats = get_document_stats()
    print(f"总chunks数量: {stats.get('total_chunks', 0)}")
    print(f"文件类型统计: {stats.get('file_types', {})}")
    print("\n测试获取文档统计信息完成")


def main():
    """主测试函数"""
    print("开始测试向量检索功能...\n")
    
    # 准备测试数据
    document_id = prepare_test_data()
    
    # 测试搜索文档
    test_search_documents()
    
    # 测试批量搜索文档
    test_batch_search_documents()
    
    # 测试根据文档ID获取文档信息
    test_get_document_by_id(document_id)
    
    # 测试获取文档统计信息
    test_get_document_stats()
    
    print("\n所有测试完成！")


if __name__ == "__main__":
    main()
