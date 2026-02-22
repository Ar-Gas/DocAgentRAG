
from pathlib import Path
from utils.storage import get_all_documents, get_document_info

print("检查所有文档信息...")
docs = get_all_documents()

for doc in docs:
    doc_id = doc.get('id')
    filename = doc.get('filename')
    filepath = doc.get('filepath')
    
    print(f"\n文档: {filename}")
    print(f"  ID: {doc_id}")
    print(f"  路径: {filepath}")
    
    if filepath:
        path_obj = Path(filepath)
        exists = path_obj.exists()
        print(f"  文件存在: {exists}")
        if exists:
            print(f"  文件大小: {path_obj.stat().st_size} 字节")
    else:
        print(f"  文件路径不存在")

