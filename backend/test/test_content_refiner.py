import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.content_refiner import ContentRefiner
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_content_refiner():
    """测试内容提炼引擎"""
    
    sample_content = """
第一章 概述

本文档介绍了文档处理系统的设计和实现。

1.1 背景

随着数字化转型的推进，文档管理变得越来越重要。企业需要高效的文档处理系统来提升工作效率。

第1页

1.2 目标

本文档的主要目标是：
- 提高文档处理效率
- 降低人工成本
- 提升文档质量

第二章 技术架构

2.1 系统架构

系统采用微服务架构，包含以下模块：
- 文档上传模块
- 内容提取模块
- 向量化模块
- 检索模块

第2页

2.2 数据存储

系统使用ChromaDB作为向量数据库，支持高效的相似度检索。

第三章 实现细节

3.1 文档处理

文档处理流程包括：
1. 文件上传
2. 内容提取
3. 噪音过滤
4. 语义分段
5. 向量化存储

3.2 性能优化

系统采用多种优化策略：
- 分块处理
- 异步处理
- 缓存机制

第四章 总结

本文档详细介绍了文档处理系统的设计和实现。通过合理的架构设计和优化策略，系统能够高效地处理各种类型的文档。

机密文档，仅供内部使用

Page 3 of 3
"""
    
    refiner = ContentRefiner()
    
    print("=" * 80)
    print("测试内容提炼引擎")
    print("=" * 80)
    
    print(f"\n原始内容长度: {len(sample_content)}")
    print("\n原始内容:")
    print("-" * 80)
    print(sample_content[:500] + "...")
    
    result = refiner.refine_document(sample_content, "test_doc_001")
    
    print(f"\n提炼后内容长度: {len(result.refined_content)}")
    print(f"内容减少比例: {result.statistics['reduction_ratio']:.2f}%")
    
    print("\n提炼后内容:")
    print("-" * 80)
    print(result.refined_content)
    
    print("\n层次结构:")
    print("-" * 80)
    print(f"总节点数: {result.statistics['hierarchy_node_count']}")
    print(f"最大深度: {result.statistics['hierarchy_depth']}")
    
    print("\n目录结构:")
    print("-" * 80)
    from utils.hierarchy_builder import HierarchyBuilder, HierarchyNode
    builder = HierarchyBuilder()
    hierarchy_root = HierarchyNode.from_dict(result.hierarchy)
    toc = builder.build_table_of_contents(hierarchy_root)
    for item in toc:
        indent = "  " * (item['level'] - 1)
        print(f"{indent}- {item['title']}")
    
    print("\n关键信息提取:")
    print("-" * 80)
    key_info = refiner.extract_key_information(sample_content)
    print(f"关键点数量: {len(key_info['key_points'])}")
    for i, point in enumerate(key_info['key_points'], 1):
        print(f"{i}. {point}")
    
    print("\n检索优化分块:")
    print("-" * 80)
    chunks = refiner.refine_for_retrieval(sample_content, "test_doc_001", chunk_size=200)
    print(f"分块数量: {len(chunks)}")
    for i, chunk in enumerate(chunks, 1):
        print(f"\n分块 {i} (长度: {chunk['chunk_length']}):")
        print(chunk['content'][:100] + "...")
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    test_content_refiner()