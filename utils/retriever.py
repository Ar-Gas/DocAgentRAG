import chromadb
import os

# 初始化Chroma数据库
client = chromadb.PersistentClient(path="./chromadb")

# 创建或获取集合
collection = client.get_or_create_collection(name="documents")

# 添加文档到向量数据库
def add_document_to_vector_db(doc_info):
    try:
        # 生成文档ID
        doc_id = doc_info['id']
        
        # 准备文档内容
        content = doc_info.get('content', '')
        filename = doc_info.get('filename', '')
        
        # 组合文本（文件名 + 内容）
        combined_text = f"{filename}\n{content}"
        
        # 添加到向量数据库
        collection.add(
            documents=[combined_text],
            metadatas=[{
                "id": doc_id,
                "filename": filename,
                "path": doc_info.get('path', ''),
                "file_type": doc_info.get('file_type', '')
            }],
            ids=[doc_id]
        )
        
        return True
    except Exception as e:
        print(f"添加文档到向量数据库失败: {str(e)}")
        return False

# 搜索文档
def search_documents(query, limit=10):
    try:
        # 执行向量搜索
        results = collection.query(
            query_texts=[query],
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )
        
        # 处理搜索结果
        search_results = []
        for i, (metadata, distance) in enumerate(zip(results['metadatas'][0], results['distances'][0])):
            search_results.append({
                "document_id": metadata['id'],
                "filename": metadata['filename'],
                "path": metadata['path'],
                "file_type": metadata['file_type'],
                "similarity": 1 - distance,  # 转换为相似度分数
                "content_snippet": results['documents'][0][i][:200] + "..." if len(results['documents'][0][i]) > 200 else results['documents'][0][i]
            })
        
        # 按相似度排序
        search_results.sort(key=lambda x: x['similarity'], reverse=True)
        
        return search_results
    except Exception as e:
        print(f"搜索文档失败: {str(e)}")
        return []

# 更新向量数据库中的文档
def update_document_in_vector_db(doc_info):
    try:
        doc_id = doc_info['id']
        content = doc_info.get('content', '')
        filename = doc_info.get('filename', '')
        
        combined_text = f"{filename}\n{content}"
        
        # 更新文档
        collection.update(
            documents=[combined_text],
            metadatas=[{
                "id": doc_id,
                "filename": filename,
                "path": doc_info.get('path', ''),
                "file_type": doc_info.get('file_type', '')
            }],
            ids=[doc_id]
        )
        
        return True
    except Exception as e:
        print(f"更新文档失败: {str(e)}")
        return False

# 删除向量数据库中的文档
def delete_document_from_vector_db(doc_id):
    try:
        collection.delete(ids=[doc_id])
        return True
    except Exception as e:
        print(f"删除文档失败: {str(e)}")
        return False
