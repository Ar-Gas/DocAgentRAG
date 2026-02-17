from .storage import init_chroma_client

# 搜索文档
def search_documents(query, limit=10):
    """
    搜索与查询相关的文档
    :param query: 查询文本
    :param limit: 返回结果数量限制
    :return: 按相似度排序的搜索结果列表
    """
    try:
        # 初始化Chroma客户端
        client = init_chroma_client()
        if not client:
            return []
        
        # 获取集合
        collection = client.get_or_create_collection(name="documents")
        
        # 执行向量搜索
        results = collection.query(
            query_texts=[query],
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )

        # 处理搜索结果
        search_results = []
        if results and results['metadatas'] and results['metadatas'][0]:
            for i, (metadata, distance) in enumerate(zip(results['metadatas'][0], results['distances'][0])):
                snippet = results['documents'][0][i]
                content_snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
                search_results.append({
                    "document_id": metadata.get('document_id', metadata.get('id', '')),
                    "filename": metadata.get('filename', ''),
                    "path": metadata.get('filepath', metadata.get('path', '')),
                    "file_type": metadata.get('file_type', ''),
                    "similarity": 1 - distance,  # 转换为相似度分数
                    "content_snippet": content_snippet,
                    "chunk_index": metadata.get('chunk_index', 0)
                })

        # 按相似度排序
        search_results.sort(key=lambda x: x['similarity'], reverse=True)

        return search_results
    except Exception as e:
        print(f"搜索文档失败: {str(e)}")
        return []

# 批量搜索文档（支持多查询）
def batch_search_documents(queries, limit=5):
    """
    批量搜索多个查询
    :param queries: 查询文本列表
    :param limit: 每个查询返回结果数量限制
    :return: 每个查询的搜索结果列表
    """
    try:
        # 初始化Chroma客户端
        client = init_chroma_client()
        if not client:
            return [[] for _ in queries]
        
        # 获取集合
        collection = client.get_or_create_collection(name="documents")
        
        # 执行批量搜索
        results = collection.query(
            query_texts=queries,
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )

        # 处理搜索结果
        batch_results = []
        for i, (metadatas, distances, documents) in enumerate(zip(results['metadatas'], results['distances'], results['documents'])):
            query_results = []
            if metadatas:
                for j, (metadata, distance) in enumerate(zip(metadatas, distances)):
                    snippet = documents[j]
                    content_snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
                    query_results.append({
                        "document_id": metadata.get('document_id', metadata.get('id', '')),
                        "filename": metadata.get('filename', ''),
                        "path": metadata.get('filepath', metadata.get('path', '')),
                        "file_type": metadata.get('file_type', ''),
                        "similarity": 1 - distance,
                        "content_snippet": content_snippet,
                        "chunk_index": metadata.get('chunk_index', 0)
                    })
            # 按相似度排序
            query_results.sort(key=lambda x: x['similarity'], reverse=True)
            batch_results.append(query_results)

        return batch_results
    except Exception as e:
        print(f"批量搜索文档失败: {str(e)}")
        return [[] for _ in queries]

# 根据文档ID获取文档信息
def get_document_by_id(document_id):
    """
    根据文档ID获取文档信息
    :param document_id: 文档ID
    :return: 文档信息
    """
    try:
        # 初始化Chroma客户端
        client = init_chroma_client()
        if not client:
            return None
        
        # 获取集合
        collection = client.get_or_create_collection(name="documents")
        
        # 查询文档
        results = collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"]
        )

        if results and results['metadatas']:
            return {
                "chunks": results['documents'],
                "metadatas": results['metadatas'],
                "ids": results['ids']
            }
        return None
    except Exception as e:
        print(f"根据ID获取文档失败: {str(e)}")
        return None

# 获取文档统计信息
def get_document_stats():
    """
    获取文档统计信息
    :return: 统计信息
    """
    try:
        # 初始化Chroma客户端
        client = init_chroma_client()
        if not client:
            return {}
        
        # 获取集合
        collection = client.get_or_create_collection(name="documents")
        
        # 获取集合中的所有文档
        results = collection.get()
        
        # 计算统计信息
        total_chunks = len(results['ids']) if results and results['ids'] else 0
        
        # 统计不同文件类型的文档数量
        file_types = {}
        if results and results['metadatas']:
            for metadata in results['metadatas']:
                file_type = metadata.get('file_type', 'unknown')
                if file_type not in file_types:
                    file_types[file_type] = 0
                file_types[file_type] += 1
        
        return {
            "total_chunks": total_chunks,
            "file_types": file_types
        }
    except Exception as e:
        print(f"获取文档统计信息失败: {str(e)}")
        return {}
