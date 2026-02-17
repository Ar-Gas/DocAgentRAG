#!/usr/bin/env python3
"""
最小化测试脚本，只测试代码语法和基本功能
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("测试导入功能...")
try:
    from utils.storage import (
        save_document_summary_for_classification,
        save_document_to_chroma,
        retrieve_from_chroma
    )
    print("导入成功！")
except Exception as e:
    print(f"导入失败: {e}")
    sys.exit(1)

print("测试文件路径...")
TEST_FILES_DIR = os.path.join(os.path.dirname(__file__), 'test_date')
print(f"测试文件目录: {TEST_FILES_DIR}")
print(f"目录存在: {os.path.exists(TEST_FILES_DIR)}")

if os.path.exists(TEST_FILES_DIR):
    print("测试文件列表:")
    for filename in os.listdir(TEST_FILES_DIR):
        filepath = os.path.join(TEST_FILES_DIR, filename)
        if os.path.isfile(filepath):
            print(f"  - {filename} ({os.path.getsize(filepath)} bytes)")

print("最小化测试完成！")
