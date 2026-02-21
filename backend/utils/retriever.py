import logging
import os
import re
import math
from collections import Counter
from chromadb.errors import InvalidCollectionException
from .storage import init_chroma_client

logger = logging.getLogger(__name__)

# ===================== BM25 关键词检索 =====================
class BM25:
    """BM25 算法实现，用于关键词精确匹配"""
    
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.doc_freqs = {}
        self.doc_len = []
        self.avgdl = 0
        self.doc_count = 0
        self.idf = {}
        self.doc_term_freqs = []
    
    def _tokenize(self, text):
        """简单分词：支持中英文"""
        text = text.lower()
        tokens = re.findall(r'[\u4e00-\u9fa5]+|[a-z0-9]+', text)
        try:
            import jieba
            new_tokens = []
            for token in tokens:
                if re.match(r'^[\u4e00-\u9fa5]+$', token):
                    new_tokens.extend(jieba.lcut(token))
                else:
                    new_tokens.append(token)
            tokens = new_tokens
        except ImportError:
            pass
        return tokens
    
    def fit(self, documents):
        """构建倒排索引"""
        self.doc_count = len(documents)
        self.doc_len = [len(self._tokenize(doc)) for doc in documents]
        self.avgdl = sum(self.doc_len) / self.doc_count if self.doc_count > 0 else 0
        
        self.doc_term_freqs = []
        for doc in documents:
            tokens = self._tokenize(doc)
            term_freq = Counter(tokens)
            self.doc_term_freqs.append(term_freq)
            
            for term in term_freq:
                if term not in self.doc_freqs:
                    self.doc_freqs[term] = 0
                self.doc_freqs[term] += 1
        
        for term, freq in self.doc_freqs.items():
            self.idf[term] = math.log((self.doc_count - freq + 0.5) / (freq + 0.5) + 1)
    
    def score(self, query, doc_idx):
        """计算单个文档的 BM25 分数"""
        query_tokens = self._tokenize(query)
        score = 0.0
        doc_len = self.doc_len[doc_idx]
        term_freqs = self.doc_term_freqs[doc_idx]
        
        for term in query_tokens:
            if term not in self.idf:
                continue
            tf = term_freqs.get(term, 0)
            idf = self.idf[term]
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl) if self.avgdl > 0 else tf
            score += idf * numerator / denominator if denominator > 0 else 0
        
        return score
    
    def search(self, query, documents, top_k=10):
        """搜索并返回排序结果"""
        if not documents or self.doc_count == 0:
            return []
        
        scores = []
        for i in range(len(documents)):
            score = self.score(query, i)
            scores.append((i, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


def hybrid_search(query, limit=10, alpha=0.5, use_rerank=True, file_types=None):
    """
    混合检索：向量检索 + BM25 关键词检索
    :param query: 查询文本
    :param limit: 返回结果数量
    :param alpha: 向量检索权重 (0-1)，1-alpha 为 BM25 权重
    :param use_rerank: 是否使用重排序
    :param file_types: 文件类型过滤
    :return: 混合检索结果
    """
    if not query or not isinstance(query, str) or limit <= 0:
        logger.error("混合检索失败：查询为空或参数非法")
        return []
    
    try:
        client = init_chroma_client()
        if not client:
            return []
        
        try:
            collection = client.get_collection(name="documents")
        except InvalidCollectionException:
            logger.warning("集合不存在，请先导入文档")
            return []
        
        search_limit = limit * 3
        
        # 1. 向量检索
        vector_results = collection.query(
            query_texts=[query],
            n_results=search_limit,
            include=["documents", "metadatas", "distances"]
        )
        
        # 2. 获取所有文档用于 BM25
        all_docs = collection.get(include=["documents", "metadatas"])
        
        if not all_docs or not all_docs.get('documents'):
            logger.warning("向量库中没有文档")
            return []
        
        # 3. BM25 关键词检索
        bm25 = BM25()
        bm25.fit(all_docs['documents'])
        bm25_scores = bm25.search(query, all_docs['documents'], top_k=search_limit)
        
        # 构建 BM25 分数字典
        bm25_score_dict = {}
        max_bm25 = max([s for _, s in bm25_scores]) if bm25_scores else 1
        for idx, score in bm25_scores:
            bm25_score_dict[idx] = score / max_bm25 if max_bm25 > 0 else 0
        
        # 4. 合并结果
        combined_results = {}
        
        # 处理向量检索结果
        if vector_results and vector_results.get('metadatas') and vector_results['metadatas'][0]:
            for i in range(len(vector_results['metadatas'][0])):
                metadata = vector_results['metadatas'][0][i]
                distance = vector_results['distances'][0][i]
                snippet = vector_results['documents'][0][i]
                
                if metadata is None:
                    continue
                
                file_type = metadata.get('file_type', '').lstrip('.')
                if file_types and file_type not in file_types:
                    continue
                
                doc_id = metadata.get('document_id', '')
                vector_score = max(0.0, min(1.0, 1 - distance))
                
                combined_results[doc_id] = {
                    "document_id": doc_id,
                    "filename": metadata.get('filename', ''),
                    "path": metadata.get('filepath', ''),
                    "file_type": metadata.get('file_type', ''),
                    "vector_score": vector_score,
                    "bm25_score": 0.0,
                    "content_snippet": snippet[:200] + "..." if len(snippet) > 200 else snippet,
                    "chunk_index": metadata.get('chunk_index', 0),
                    "full_content": snippet
                }
        
        # 处理 BM25 结果
        for idx, score in bm25_scores:
            if idx >= len(all_docs['documents']):
                continue
            metadata = all_docs['metadatas'][idx] if all_docs.get('metadatas') and idx < len(all_docs['metadatas']) else {}
            doc_id = metadata.get('document_id', '') if metadata else ''
            
            file_type = metadata.get('file_type', '').lstrip('.') if metadata else ''
            if file_types and file_type not in file_types:
                continue
            
            normalized_score = score / max_bm25 if max_bm25 > 0 else 0
            snippet = all_docs['documents'][idx]
            
            if doc_id in combined_results:
                combined_results[doc_id]['bm25_score'] = normalized_score
            else:
                combined_results[doc_id] = {
                    "document_id": doc_id,
                    "filename": metadata.get('filename', '') if metadata else '',
                    "path": metadata.get('filepath', '') if metadata else '',
                    "file_type": metadata.get('file_type', '') if metadata else '',
                    "vector_score": 0.0,
                    "bm25_score": normalized_score,
                    "content_snippet": snippet[:200] + "..." if len(snippet) > 200 else snippet,
                    "chunk_index": metadata.get('chunk_index', 0) if metadata else 0,
                    "full_content": snippet
                }
        
        # 5. 计算混合分数
        for doc_id, result in combined_results.items():
            result['similarity'] = alpha * result['vector_score'] + (1 - alpha) * result['bm25_score']
        
        # 6. 排序并限制数量
        results = list(combined_results.values())
        results.sort(key=lambda x: x['similarity'], reverse=True)
        results = results[:limit]
        
        # 7. 重排序
        if use_rerank and results:
            results = rerank_documents(query, results, top_k=limit)
        
        # 清理内部字段
        for result in results:
            result.pop('full_content', None)
            result.pop('vector_score', None)
            result.pop('bm25_score', None)
        
        logger.info(f"混合检索完成: 向量权重={alpha}, 返回{len(results)}条结果")
        return results
        
    except Exception as e:
        logger.error(f"混合检索失败: {str(e)}")
        return []

# 检索结果重排序
def rerank_documents(query, results, top_k=None):
    """
    使用Cross-Encoder对检索结果进行重排序
    :param query: 查询文本
    :param results: 初始检索结果列表
    :param top_k: 返回前k个结果，None表示返回全部
    :return: 重排序后的结果列表
    """
    if not results:
        return results

    try:
        from sentence_transformers import CrossEncoder

        model_name = os.getenv('RERANK_MODEL', 'BAAI/bge-reranker-base')
        logger.info(f"使用重排序模型: {model_name}")

        cross_encoder = CrossEncoder(model_name)

        doc_pairs = [(query, doc.get('content_snippet', '')) for doc in results]

        scores = cross_encoder.predict(doc_pairs)

        for i, doc in enumerate(results):
            doc['rerank_score'] = float(scores[i])
            doc['original_similarity'] = doc.get('similarity', 0)
            doc['similarity'] = float(scores[i])

        results.sort(key=lambda x: x['similarity'], reverse=True)

        if top_k and top_k < len(results):
            results = results[:top_k]

        logger.info(f"重排序完成，返回 {len(results)} 条结果")
        return results

    except ImportError:
        logger.warning("sentence-transformers未安装，跳过重排序")
        return results
    except Exception as e:
        logger.error(f"重排序失败: {str(e)}")
        return results


# 搜索文档
def search_documents(query, limit=10, use_rerank=False, file_types=None):
    """
    搜索与查询相关的文档
    :param query: 查询文本
    :param limit: 返回结果数量限制
    :param use_rerank: 是否使用重排序
    :param file_types: 文件类型过滤列表，如 ['pdf', 'docx']
    :return: 按相似度排序的搜索结果列表
    """
    # 参数校验
    if not query or not isinstance(query, str) or limit <= 0:
        logger.error("搜索失败：查询为空或结果数非法")
        return []

    # 扩大检索范围，以便过滤后仍有足够结果
    search_limit = limit * 3 if file_types else limit

    try:
        client = init_chroma_client()
        if not client:
            return []

        # 仅获取集合，不创建
        try:
            collection = client.get_collection(name="documents")
        except InvalidCollectionException:
            logger.warning("集合不存在，请先导入文档")
            return []

        # 执行向量搜索
        results = collection.query(
            query_texts=[query],
            n_results=search_limit,
            include=["documents", "metadatas", "distances"]
        )

        # 处理搜索结果
        search_results = []
        # 校验结果完整性
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

                # 元数据空值处理
                if metadata is None:
                    continue

                # 文件类型过滤
                if file_types:
                    file_type = metadata.get('file_type', '').lstrip('.')
                    if file_type not in file_types:
                        continue

                # 截取内容片段
                content_snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
                # 相似度边界限制
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

        # 限制返回数量
        search_results = search_results[:limit]

        # 使用重排序模型优化结果顺序
        if use_rerank and search_results:
            search_results = rerank_documents(query, search_results, top_k=limit)

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
        except InvalidCollectionException:
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
        except InvalidCollectionException:
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
        except InvalidCollectionException:
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