#!/usr/bin/env python3
"""
测试Chroma存储功能
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def test_save_to_chroma():
    """测试保存文档到Chroma"""
    print("测试保存文档到Chroma...")
    test_files = get_test_files()
    
    # 先测试一个较小的文件
    small_file = None
    for filepath in test_files:
        if os.path.getsize(filepath) < 10000:  # 选择小于10KB的文件
            small_file = filepath
            break
    
    if small_file:
        print(f"\n测试文件: {small_file}")
        # 先保存摘要获取document_id
        document_id, _ = save_document_summary_for_classification(small_file)
        if document_id:
            print(f"获取document_id成功: {document_id}")
            print("正在保存到Chroma...")
            success = save_document_to_chroma(small_file, document_id)
            if success:
                print(f"成功保存文档到Chroma: {small_file}")
            else:
                print(f"保存文档到Chroma失败: {small_file}")
        else:
            print(f"获取document_id失败: {small_file}")
    else:
        print("未找到合适的测试文件")
    print("\n测试保存文档到Chroma完成\n")


def main():
    """主测试函数"""
    print("开始测试Chroma存储功能...\n")
    
    # 测试保存文档到Chroma
    test_save_to_chroma()
    
    print("所有测试完成！")


if __name__ == "__main__":
    main()
