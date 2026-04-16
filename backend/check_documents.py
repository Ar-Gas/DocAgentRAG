
from pathlib import Path

from app.infra.repositories.document_repository import DocumentRepository
from config import DATA_DIR


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def get_all_documents():
    return _document_repository().list_all()


def get_document_info(document_id: str):
    return _document_repository().get(document_id)

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
