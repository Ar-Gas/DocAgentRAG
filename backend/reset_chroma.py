#!/usr/bin/env python3
import os
import shutil
from pathlib import Path
from chromadb import PersistentClient
from config import CHROMA_DB_PATH

print(f"正在重置 ChromaDB: {CHROMA_DB_PATH}")

if os.path.exists(CHROMA_DB_PATH):
    print(f"删除旧的 ChromaDB 数据...")
    shutil.rmtree(CHROMA_DB_PATH)

print(f"重新创建目录...")
os.makedirs(CHROMA_DB_PATH, exist_ok=True)

print("ChromaDB 已重置完成！")
print("现在重启后端服务即可使用新的 2048 维嵌入")
