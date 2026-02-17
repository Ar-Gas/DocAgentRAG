#!/usr/bin/env python3
# 测试分类功能

import sys
import os

# 添加项目路径
sys.path.append('/root/autodl-tmp/DocAgentRAG/backend')

print("测试分类功能")
print("=" * 50)

# 测试1: 导入测试
try:
    from utils.classifier import classify_with_llm, rag_enhanced_classification, classify_document
    print("✓ 成功导入分类模块")
except Exception as e:
    print(f"✗ 导入失败: {str(e)}")
    sys.exit(1)

# 测试2: 基本分类测试
try:
    test_content = "这是一份财务报告，包含了2024年第一季度的财务数据和分析。"
    categories = classify_with_llm(test_content)
    print(f"✓ 基本分类测试成功")
    print(f"  分类结果: {categories}")
except Exception as e:
    print(f"✗ 基本分类测试失败: {str(e)}")

# 测试3: RAG增强分类测试
try:
    test_doc_info = {
        'content': "这是一份技术文档，包含了系统架构设计和开发指南。",
        'filename': "技术架构文档.pdf"
    }
    rag_result = rag_enhanced_classification(test_doc_info)
    print(f"✓ RAG增强分类测试成功")
    print(f"  分类结果: {rag_result['categories']}")
    print(f"  置信度: {rag_result['confidence']}")
except Exception as e:
    print(f"✗ RAG增强分类测试失败: {str(e)}")

# 测试4: 完整分类流水线测试
try:
    test_doc_info = {
        'id': "test-001",
        'content': "这是一份会议纪要，记录了2024年2月18日的项目讨论。",
        'filename': "项目会议纪要.docx"
    }
    final_result = classify_document(test_doc_info)
    print(f"✓ 完整分类流水线测试成功")
    print(f"  文档ID: {final_result['document_id']}")
    print(f"  分类结果: {final_result['classification_result']['categories']}")
except Exception as e:
    print(f"✗ 完整分类流水线测试失败: {str(e)}")

print("=" * 50)
print("测试完成")
