import logging
from chromadb.errors import NotFoundError
from .storage import init_chroma_client

# ===================== 规范：用 logging 替代 print =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 搜索文档
def search_documents(query, limit=10):
    """
    搜索与查询相关的文档
    :param query: 查询文本
    :param limit: 返回结果数量限制
    :return: 按相似度排序的搜索结果列表
    """
    # ===================== 优化1：参数校验 =====================
    if not query or not isinstance(query, str) or limit <= 0:
        logger.error("搜索失败：查询为空或结果数非法")
        return []

    try:
        client = init_chroma_client()
        if not client:
            return []

        # ===================== 修复1：仅获取集合，不创建 =====================
        try:
            collection = client.get_collection(name="documents")
        except NotFoundError:
            logger.warning("集合不存在，请先导入文档")
            return []

        # 执行向量搜索
        results = collection.query(
            query_texts=[query],
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )

        # 处理搜索结果
        search_results = []
        # ===================== 修复2：校验结果完整性 =====================
        if (results and 
            results.get('metadatas') and 
            results['metadatas'][0] and 
            results.get('documents') and 
            results['documents'][0] and
            results.get('distances') and 
            results['distances'][0]):
            
            # 确保三个列表长度一致
            min_len = min(len(results['metadatas'][0]), len(results['distances'][0]), len(results['documents'][0]))
            for i in range(min_len):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]
                snippet = results['documents'][0][i]

                # ===================== 优化2：元数据空值处理 =====================
                if metadata is None:
                    continue

                # 截取内容片段
                content_snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
                # ===================== 修复3：相似度边界限制 =====================
                similarity = max(0.0, min(1.0, 1 - distance))

                search_results.append({
                    "document_id": metadata.get('document_id', metadata.get('id', '')),
                    "filename": metadata.get('filename', ''),
                    "path": metadata.get('filepath', metadata.get('path', '')),
                    "file_type": metadata.get('file_type', ''),
                    "similarity": similarity,
                    "content_snippet": content_snippet,
                    "chunk_index": metadata.get('chunk_index', 0)
                })

        # 按相似度排序
        search_results.sort(key=lambda x: x['similarity'], reverse=True)
        logger.info(f"搜索完成，返回 {len(search_results)} 条结果")
        return search_results
    except Exception as e:
        logger.error(f"搜索文档失败: {str(e)}")
        return []

# 批量搜索文档（支持多查询）
def batch_search_documents(queries, limit=5):
    """
    批量搜索多个查询
    :param queries: 查询文本列表
    :param limit: 每个查询返回结果数量限制
    :return: 每个查询的搜索结果列表
    """
    # ===================== 优化1：参数校验 =====================
    if not isinstance(queries, list) or len(queries) == 0 or limit <= 0:
        logger.error("批量搜索失败：查询列表为空或结果数非法")
        return []

    try:
        client = init_chroma_client()
        if not client:
            return [[] for _ in queries]

        # ===================== 修复1：仅获取集合，不创建 =====================
        try:
            collection = client.get_collection(name="documents")
        except NotFoundError:
            logger.warning("集合不存在，请先导入文档")
            return [[] for _ in queries]

        # 执行批量搜索
        results = collection.query(
            query_texts=queries,
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )

        # 处理搜索结果
        batch_results = []
        # ===================== 修复2：校验结果完整性 =====================
        metadatas_list = results.get('metadatas', [])
        distances_list = results.get('distances', [])
        documents_list = results.get('documents', [])

        # 确保三个列表长度一致
        min_query_len = min(len(metadatas_list), len(distances_list), len(documents_list))
        for i in range(min_query_len):
            metadatas = metadatas_list[i] or []
            distances = distances_list[i] or []
            documents = documents_list[i] or []
            query_results = []

            # 确保单条查询的三个列表长度一致
            min_chunk_len = min(len(metadatas), len(distances), len(documents))
            for j in range(min_chunk_len):
                metadata = metadatas[j]
                distance = distances[j]
                snippet = documents[j]

                if metadata is None:
                    continue

                content_snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
                similarity = max(0.0, min(1.0, 1 - distance))

                query_results.append({
                    "document_id": metadata.get('document_id', metadata.get('id', '')),
                    "filename": metadata.get('filename', ''),
                    "path": metadata.get('filepath', metadata.get('path', '')),
                    "file_type": metadata.get('file_type', ''),
                    "similarity": similarity,
                    "content_snippet": content_snippet,
                    "chunk_index": metadata.get('chunk_index', 0)
                })

            # 按相似度排序
            query_results.sort(key=lambda x: x['similarity'], reverse=True)
            batch_results.append(query_results)

        # 补全剩余查询的空结果
        while len(batch_results) < len(queries):
            batch_results.append([])

        logger.info(f"批量搜索完成，处理 {len(batch_results)} 条查询")
        return batch_results
    except Exception as e:
        logger.error(f"批量搜索文档失败: {str(e)}")
        return [[] for _ in queries]

# 根据文档ID获取文档信息
def get_document_by_id(document_id):
    """
    根据文档ID获取文档信息
    :param document_id: 文档ID
    :return: 文档信息
    """
    # ===================== 优化1：参数校验 =====================
    if not document_id or not isinstance(document_id, str):
        logger.error("根据ID获取文档失败：文档ID为空或非法")
        return None

    try:
        client = init_chroma_client()
        if not client:
            return None

        # ===================== 修复1：仅获取集合，不创建 =====================
        try:
            collection = client.get_collection(name="documents")
        except NotFoundError:
            logger.warning("集合不存在，请先导入文档")
            return None

        # 查询文档
        results = collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"]
        )

        if results and results.get('metadatas') and len(results['metadatas']) > 0:
            logger.info(f"根据ID获取文档成功：{document_id}，共 {len(results['ids'])} 个分片")
            return {
                "chunks": results.get('documents', []),
                "metadatas": results.get('metadatas', []),
                "ids": results.get('ids', [])
            }
        return None
    except Exception as e:
        logger.error(f"根据ID获取文档失败: {str(e)}")
        return None

# 获取文档统计信息
def get_document_stats():
    """
    获取文档统计信息（优化内存占用）
    :return: 统计信息
    """
    try:
        client = init_chroma_client()
        if not client:
            return {}

        # ===================== 修复1：仅获取集合，不创建 =====================
        try:
            collection = client.get_collection(name="documents")
        except NotFoundError:
            logger.warning("集合不存在，请先导入文档")
            return {"total_chunks": 0, "file_types": {}}

        # ===================== 修复2：用 count() 替代 get()，避免内存溢出 =====================
        total_chunks = collection.count()

        # 统计不同文件类型的文档数量（仅获取元数据，不获取文档内容）
        file_types = {}
        if total_chunks > 0:
            # 分批获取元数据，避免一次性加载过多
            batch_size = 1000
            for offset in range(0, total_chunks, batch_size):
                results = collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=["metadatas"]  # 仅获取元数据，不获取文档内容
                )
                if results and results.get('metadatas'):
                    for metadata in results['metadatas']:
                        if metadata is None:
                            continue
                        file_type = metadata.get('file_type', 'unknown')
                        file_types[file_type] = file_types.get(file_type, 0) + 1

        stats = {
            "total_chunks": total_chunks,
            "file_types": file_types
        }
        logger.info(f"获取统计信息成功：{stats}")
        return stats
    except Exception as e:
        logger.error(f"获取文档统计信息失败: {str(e)}")
        return {}