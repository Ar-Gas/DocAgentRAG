import logging
import os
import re
import math
import base64
import hashlib
from collections import Counter
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from .storage import init_chroma_client, doubao_multimodal_embed, DOUBAO_EMBEDDING_MODEL

logger = logging.getLogger(__name__)


# ===================== BM25 索引缓存 =====================
_bm25_cache = None
_bm25_cache_hash = None
_bm25_doc_count = 0


def _compute_docs_hash(documents: List[str]) -> str:
    """计算文档集合的哈希值"""
    content = f"{len(documents)}:{documents[0][:100] if documents else ''}"
    return hashlib.md5(content.encode()).hexdigest()


def get_cached_bm25_index(documents: List[str], bm25_class):
    """
    获取缓存的 BM25 索引，如果缓存失效则重新构建
    
    :param documents: 文档列表
    :param bm25_class: BM25 类
    :return: BM25 索引实例
    """
    global _bm25_cache, _bm25_cache_hash, _bm25_doc_count
    
    current_hash = _compute_docs_hash(documents)
    current_doc_count = len(documents)
    
    if (_bm25_cache is not None and
        _bm25_cache_hash == current_hash and
        _bm25_doc_count == current_doc_count):
        logger.debug("使用缓存的 BM25 索引")
        return _bm25_cache
    
    logger.info("重新构建 BM25 索引")
    bm25 = bm25_class()
    bm25.fit(documents)
    _bm25_cache = bm25
    _bm25_cache_hash = current_hash
    _bm25_doc_count = current_doc_count
    return bm25


# ===================== 查询解析器 =====================
@dataclass
class ParsedQuery:
    """解析后的查询结构"""
    original_query: str
    exact_phrases: List[str]
    exclude_terms: List[str]
    include_terms: List[str]
    fuzzy_terms: List[str]
    file_types: List[str]
    date_range: Optional[Tuple[str, str]]
    is_advanced: bool = False


class SearchQueryParser:
    """检索查询解析器 - 支持百度式语法"""
    
    def __init__(self):
        pass
    
    def parse(self, query: str) -> ParsedQuery:
        """
        解析查询字符串
        
        支持的语法：
        - "关键词" : 模糊匹配
        - \"精确短语\" : 精确匹配
        - -排除词 : 排除指定词
        - filetype:pdf : 文件类型过滤
        - ~模糊词~ : 模糊匹配（波浪线）
        """
        if not query or not query.strip():
            return ParsedQuery(
                original_query="",
                exact_phrases=[],
                exclude_terms=[],
                include_terms=[],
                fuzzy_terms=[],
                file_types=[],
                date_range=None
            )
        
        original_query = query.strip()
        
        # 提取精确短语（双引号包裹）
        exact_phrases = []
        exact_pattern = r'"([^"]+)"'
        for match in re.finditer(exact_pattern, original_query):
            exact_phrases.append(match.group(1).strip())
        query_without_exact = re.sub(exact_pattern, '', original_query)
        
        # 提取排除词（-开头）
        exclude_terms = []
        exclude_pattern = r'-(\S+)'
        for match in re.finditer(exclude_pattern, query_without_exact):
            exclude_terms.append(match.group(1).strip())
        query_without_exclude = re.sub(exclude_pattern, '', query_without_exact)
        
        # 提取文件类型（filetype:xxx）
        file_types = []
        filetype_pattern = r'filetype:(\S+)'
        for match in re.finditer(filetype_pattern, query_without_exclude):
            ft = match.group(1).strip().lower().lstrip('.')
            if ft:
                file_types.append(ft)
        query_without_filetype = re.sub(filetype_pattern, '', query_without_exclude)
        
        # 提取模糊词（~xxx~）
        fuzzy_terms = []
        fuzzy_pattern = r'~([^~]+)~'
        for match in re.finditer(fuzzy_pattern, query_without_filetype):
            fuzzy_terms.append(match.group(1).strip())
        query_without_fuzzy = re.sub(fuzzy_pattern, '', query_without_filetype)
        
        # 剩余的作为包含词
        include_terms = self._extract_terms(query_without_fuzzy)
        
        is_advanced = (
            len(exact_phrases) > 0 or
            len(exclude_terms) > 0 or
            len(file_types) > 0 or
            len(fuzzy_terms) > 0
        )
        
        return ParsedQuery(
            original_query=original_query,
            exact_phrases=exact_phrases,
            exclude_terms=exclude_terms,
            include_terms=include_terms,
            fuzzy_terms=fuzzy_terms,
            file_types=file_types,
            date_range=None,
            is_advanced=is_advanced
        )
    
    def _extract_terms(self, text: str) -> List[str]:
        """从文本中提取检索词"""
        text = re.sub(r'\s+', ' ', text).strip()
        terms = []
        try:
            import jieba
            terms = [w.strip() for w in jieba.lcut(text) if len(w.strip()) > 0]
        except ImportError:
            terms = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z0-9]+', text)
            terms = [w for w in terms if len(w) > 0]
        return terms
    
    def get_search_string(self, parsed: ParsedQuery) -> str:
        """生成用于检索的查询字符串"""
        parts = []
        parts.extend(parsed.include_terms)
        parts.extend(parsed.exact_phrases)
        parts.extend(parsed.fuzzy_terms)
        return ' '.join(parts)
    
    def should_exclude(self, content: str, parsed: ParsedQuery) -> bool:
        """判断内容是否应该被排除"""
        if not parsed.exclude_terms:
            return False
        content_lower = content.lower()
        for term in parsed.exclude_terms:
            if term.lower() in content_lower:
                return True
        return False
    
    def has_exact_match(self, content: str, parsed: ParsedQuery) -> bool:
        """判断内容是否包含精确短语"""
        if not parsed.exact_phrases:
            return False
        content_lower = content.lower()
        for phrase in parsed.exact_phrases:
            if phrase.lower() in content_lower:
                return True
        return False


# 全局查询解析器实例
_query_parser = SearchQueryParser()


def get_query_parser() -> SearchQueryParser:
    """获取全局查询解析器实例"""
    return _query_parser


def highlight_keywords(text: str, keywords: List[str], max_highlights: int = 10) -> Tuple[str, List[Dict]]:
    """
    在文本中高亮匹配的关键词
    
    :param text: 原始文本
    :param keywords: 关键词列表
    :param max_highlights: 最大高亮数量
    :return: (高亮后的文本, 高亮信息列表)
    """
    if not text or not keywords:
        return text, []
    
    highlights = []
    highlighted_text = text
    
    # 对关键词按长度降序排序，优先匹配更长的词
    sorted_keywords = sorted(keywords, key=len, reverse=True)
    
    for keyword in sorted_keywords:
        if not keyword.strip():
            continue
        
        # 不区分大小写匹配
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        
        matches = list(pattern.finditer(text))
        if matches:
            for match in matches[:max_highlights]:
                highlights.append({
                    'keyword': keyword,
                    'start': match.start(),
                    'end': match.end(),
                    'matched_text': match.group()
                })
    
    # 按位置排序并限制数量
    highlights = sorted(highlights, key=lambda x: x['start'])[:max_highlights]
    
    # 生成带高亮标记的文本
    if highlights:
        result_parts = []
        last_end = 0
        for h in highlights:
            result_parts.append(text[last_end:h['start']])
            result_parts.append(f"<mark class='highlight'>{h['matched_text']}</mark>")
            last_end = h['end']
        result_parts.append(text[last_end:])
        highlighted_text = ''.join(result_parts)
    
    return highlighted_text, highlights


def search_with_highlight(
    query: str, 
    search_type: str = 'hybrid',
    limit: int = 10, 
    alpha: float = 0.5,
    use_rerank: bool = False,
    file_types: Optional[List[str]] = None
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    带关键词高亮的检索功能
    
    :param query: 查询文本
    :param search_type: 检索类型 ('keyword', 'vector', 'hybrid', 'smart')
    :param limit: 返回结果数量
    :param alpha: 混合检索权重
    :param use_rerank: 是否使用重排序
    :param file_types: 文件类型过滤
    :return: (检索结果列表, 元信息)
    """
    # 提取查询中的关键词（分词）
    keywords = []
    try:
        import jieba
        keywords = [w.strip() for w in jieba.lcut(query) if len(w.strip()) > 1]
    except ImportError:
        # 如果没有 jieba，使用简单的正则分词
        keywords = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z0-9]+', query)
        keywords = [w for w in keywords if len(w) > 1]
    
    # 执行对应的检索
    if search_type == 'keyword':
        results = keyword_search(query, limit, file_types)
    elif search_type == 'vector':
        results = search_documents(query, limit, use_rerank, file_types)
    elif search_type == 'hybrid':
        results = hybrid_search(query, limit, alpha, use_rerank, file_types)
    else:
        # smart 类型需要特殊的处理函数，这里默认用 hybrid
        results = hybrid_search(query, limit, alpha, use_rerank, file_types)
    
    # 为每个结果添加高亮
    for result in results:
        highlighted_text, highlights = highlight_keywords(
            result.get('content_snippet', ''), 
            keywords
        )
        result['content_snippet'] = highlighted_text
        result['highlights'] = highlights
        result['matched_keywords'] = list(set([h['keyword'] for h in highlights]))
    
    meta_info = {
        'search_type': search_type,
        'query': query,
        'keywords': keywords,
        'total_results': len(results)
    }
    
    return results, meta_info


def keyword_search(query: str, limit: int = 10, file_types: Optional[List[str]] = None) -> List[Dict]:
    """
    精确关键词检索：仅使用 BM25 算法进行关键词匹配
    支持百度式检索语法（精确匹配、排除词、文件类型过滤）
    
    :param query: 查询文本
    :param limit: 返回结果数量
    :param file_types: 文件类型过滤
    :return: 检索结果列表
    """
    if not query or not isinstance(query, str) or limit <= 0:
        logger.error("关键词检索失败：查询为空或参数非法")
        return []
    
    # 使用查询解析器解析查询
    parser = get_query_parser()
    parsed = parser.parse(query)
    search_str = parser.get_search_string(parsed)
    
    # 合并文件类型过滤
    final_file_types = file_types or []
    if parsed.file_types:
        final_file_types.extend(parsed.file_types)
        final_file_types = list(set(final_file_types))
    
    try:
        client, collection = init_chroma_client()
        if not client or not collection:
            logger.error("初始化Chroma客户端失败")
            return []
        
        # 获取所有文档
        all_docs = collection.get(include=["documents", "metadatas"])
        
        if not all_docs or not all_docs.get('documents'):
            logger.warning("向量库中没有文档")
            return []
        
        # 使用缓存的 BM25 进行关键词检索
        bm25 = get_cached_bm25_index(all_docs['documents'], BM25)
        bm25_scores = bm25.search(search_str, all_docs['documents'], top_k=limit * 3)
        
        if not bm25_scores:
            logger.info("关键词检索无结果")
            return []
        
        max_bm25 = max([s for _, s in bm25_scores]) if bm25_scores else 1
        
        search_results = []
        for idx, score in bm25_scores:
            if idx >= len(all_docs['documents']):
                continue
            
            metadata = all_docs['metadatas'][idx] if all_docs.get('metadatas') and idx < len(all_docs['metadatas']) else {}
            
            if metadata is None:
                continue
            
            snippet = all_docs['documents'][idx]
            
            # 应用排除词过滤
            if parser.should_exclude(snippet, parsed):
                continue
            
            # 文件类型过滤
            file_type = metadata.get('file_type', '').lstrip('.')
            if final_file_types and file_type not in final_file_types:
                continue
            
            normalized_score = score / max_bm25 if max_bm25 > 0 else 0
            
            search_results.append({
                "document_id": metadata.get('document_id', ''),
                "filename": metadata.get('filename', ''),
                "path": metadata.get('filepath', ''),
                "file_type": metadata.get('file_type', ''),
                "similarity": normalized_score,
                "content_snippet": snippet[:200] + "..." if len(snippet) > 200 else snippet,
                "chunk_index": metadata.get('chunk_index', 0),
                "has_exact_match": parser.has_exact_match(snippet, parsed)
            })
        
        # 按分数排序（精确匹配优先）
        search_results.sort(
            key=lambda x: (x.get('has_exact_match', False), x['similarity']),
            reverse=True
        )
        search_results = search_results[:limit]
        
        logger.info(f"关键词检索完成: query='{query[:50]}...', results={len(search_results)}")
        return search_results
        
    except Exception as e:
        logger.error(f"关键词检索失败: {str(e)}")
        return []

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


def get_query_embedding(query: str, image_url: Optional[str] = None, 
                        image_path: Optional[str] = None) -> Optional[List[float]]:
    """
    使用豆包API获取查询的嵌入向量（支持多模态）
    
    :param query: 查询文本
    :param image_url: 图片URL（可选）
    :param image_path: 图片本地路径（可选）
    :return: 嵌入向量
    """
    if image_path:
        try:
            with open(image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
            return doubao_multimodal_embed(query, image_base64=image_base64)
        except Exception as e:
            logger.error(f"读取图片失败: {str(e)}")
    
    if image_url:
        return doubao_multimodal_embed(query, image_url=image_url)
    
    return doubao_multimodal_embed(query)


def multimodal_search(
    query: str,
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
    limit: int = 10,
    file_types: Optional[List[str]] = None
) -> List[Dict]:
    """
    多模态检索：支持文本+图片联合查询
    
    :param query: 查询文本
    :param image_url: 图片URL（可选）
    :param image_path: 图片本地路径（可选）
    :param limit: 返回结果数量
    :param file_types: 文件类型过滤
    :return: 检索结果列表
    """
    if not query and not image_url and not image_path:
        logger.error("多模态检索失败：查询内容为空")
        return []
    
    try:
        client, collection = init_chroma_client()
        if not client or not collection:
            logger.error("初始化Chroma客户端失败")
            return []
        
        query_embedding = get_query_embedding(query, image_url, image_path)
        
        if query_embedding is None:
            logger.warning("豆包嵌入失败，回退到文本检索")
            return search_documents(query, limit=limit, file_types=file_types)
        
        search_limit = limit * 3 if file_types else limit
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=search_limit,
            include=["documents", "metadatas", "distances"]
        )
        
        search_results = []
        
        if (results and results.get('metadatas') and results['metadatas'][0] and
            results.get('documents') and results['documents'][0] and
            results.get('distances') and results['distances'][0]):
            
            min_len = min(
                len(results['metadatas'][0]),
                len(results['distances'][0]),
                len(results['documents'][0])
            )
            
            for i in range(min_len):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]
                snippet = results['documents'][0][i]
                
                if metadata is None:
                    continue
                
                if file_types:
                    file_type = metadata.get('file_type', '').lstrip('.')
                    if file_type not in file_types:
                        continue
                
                content_snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
                similarity = max(0.0, min(1.0, 1 - distance))
                
                search_results.append({
                    "document_id": metadata.get('document_id', ''),
                    "filename": metadata.get('filename', ''),
                    "path": metadata.get('filepath', ''),
                    "file_type": metadata.get('file_type', ''),
                    "similarity": similarity,
                    "content_snippet": content_snippet,
                    "chunk_index": metadata.get('chunk_index', 0),
                    "embedding_model": DOUBAO_EMBEDDING_MODEL,
                    "multimodal_query": bool(image_url or image_path)
                })
        
        search_results.sort(key=lambda x: x['similarity'], reverse=True)
        search_results = search_results[:limit]
        
        logger.info(f"多模态检索完成: query='{query[:50]}...', has_image={bool(image_url or image_path)}, results={len(search_results)}")
        return search_results
        
    except Exception as e:
        logger.error(f"多模态检索失败: {str(e)}")
        return []


def hybrid_multimodal_search(
    query: str,
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
    limit: int = 10,
    alpha: float = 0.5,
    use_rerank: bool = True,
    file_types: Optional[List[str]] = None
) -> List[Dict]:
    """
    混合多模态检索：向量检索 + BM25 关键词检索，支持图片输入
    
    :param query: 查询文本
    :param image_url: 图片URL（可选）
    :param image_path: 图片本地路径（可选）
    :param limit: 返回结果数量
    :param alpha: 向量检索权重 (0-1)
    :param use_rerank: 是否使用重排序
    :param file_types: 文件类型过滤
    :return: 混合检索结果
    """
    if not query and not image_url and not image_path:
        logger.error("混合多模态检索失败：查询内容为空")
        return []
    
    try:
        client, collection = init_chroma_client()
        if not client or not collection:
            return []
        
        search_limit = limit * 3
        
        query_embedding = get_query_embedding(query, image_url, image_path)
        
        if query_embedding is None:
            logger.warning("豆包嵌入失败，回退到普通混合检索")
            return hybrid_search(query, limit=limit, alpha=alpha, use_rerank=use_rerank, file_types=file_types)
        
        vector_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=search_limit,
            include=["documents", "metadatas", "distances"]
        )
        
        all_docs = collection.get(include=["documents", "metadatas"])
        
        if not all_docs or not all_docs.get('documents'):
            logger.warning("向量库中没有文档")
            return []
        
        bm25 = BM25()
        bm25.fit(all_docs['documents'])
        bm25_scores = bm25.search(query, all_docs['documents'], top_k=search_limit) if query else []
        
        bm25_score_dict = {}
        max_bm25 = max([s for _, s in bm25_scores]) if bm25_scores else 1
        for idx, score in bm25_scores:
            bm25_score_dict[idx] = score / max_bm25 if max_bm25 > 0 else 0
        
        combined_results = {}
        
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
                    "full_content": snippet,
                    "embedding_model": DOUBAO_EMBEDDING_MODEL,
                    "multimodal_query": bool(image_url or image_path)
                }
        
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
                    "full_content": snippet,
                    "embedding_model": DOUBAO_EMBEDDING_MODEL,
                    "multimodal_query": bool(image_url or image_path)
                }
        
        for doc_id, result in combined_results.items():
            result['similarity'] = alpha * result['vector_score'] + (1 - alpha) * result['bm25_score']
        
        results = list(combined_results.values())
        results.sort(key=lambda x: x['similarity'], reverse=True)
        results = results[:limit]
        
        if use_rerank and results:
            results = rerank_documents(query, results, top_k=limit)
        
        for result in results:
            result.pop('full_content', None)
            result.pop('vector_score', None)
            result.pop('bm25_score', None)
        
        logger.info(f"混合多模态检索完成: has_image={bool(image_url or image_path)}, results={len(results)}")
        return results
        
    except Exception as e:
        logger.error(f"混合多模态检索失败: {str(e)}")
        return []


def hybrid_search(query, limit=10, alpha=0.5, use_rerank=True, file_types=None):
    """
    混合检索：向量检索 + BM25 关键词检索
    支持百度式检索语法（精确匹配、排除词、文件类型过滤）
    
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
    
    # 使用查询解析器解析查询
    parser = get_query_parser()
    parsed = parser.parse(query)
    search_str = parser.get_search_string(parsed)
    
    # 合并文件类型过滤
    final_file_types = file_types or []
    if parsed.file_types:
        final_file_types.extend(parsed.file_types)
        final_file_types = list(set(final_file_types))
    
    try:
        client, collection = init_chroma_client()
        if not client or not collection:
            logger.error("初始化Chroma客户端失败")
            return []
        
        search_limit = limit * 3
        
        # 1. 向量检索
        vector_results = collection.query(
            query_texts=[search_str],
            n_results=search_limit,
            include=["documents", "metadatas", "distances"]
        )
        
        # 2. 获取所有文档用于 BM25
        all_docs = collection.get(include=["documents", "metadatas"])
        
        if not all_docs or not all_docs.get('documents'):
            logger.warning("向量库中没有文档")
            return []
        
        # 3. BM25 关键词检索（使用缓存）
        bm25 = get_cached_bm25_index(all_docs['documents'], BM25)
        bm25_scores = bm25.search(search_str, all_docs['documents'], top_k=search_limit)
        
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
                
                # 应用排除词过滤
                if parser.should_exclude(snippet, parsed):
                    continue
                
                # 文件类型过滤
                file_type = metadata.get('file_type', '').lstrip('.')
                if final_file_types and file_type not in final_file_types:
                    continue
                
                doc_id = metadata.get('document_id', '') + '_' + str(metadata.get('chunk_index', 0))
                vector_score = max(0.0, min(1.0, 1 - distance))
                
                combined_results[doc_id] = {
                    "document_id": metadata.get('document_id', ''),
                    "filename": metadata.get('filename', ''),
                    "path": metadata.get('filepath', ''),
                    "file_type": metadata.get('file_type', ''),
                    "vector_score": vector_score,
                    "bm25_score": 0.0,
                    "content_snippet": snippet[:200] + "..." if len(snippet) > 200 else snippet,
                    "chunk_index": metadata.get('chunk_index', 0),
                    "full_content": snippet,
                    "has_exact_match": parser.has_exact_match(snippet, parsed)
                }
        
        # 处理 BM25 结果
        for idx, score in bm25_scores:
            if idx >= len(all_docs['documents']):
                continue
            metadata = all_docs['metadatas'][idx] if all_docs.get('metadatas') and idx < len(all_docs['metadatas']) else {}
            if not metadata:
                continue
            
            snippet = all_docs['documents'][idx]
            
            # 应用排除词过滤
            if parser.should_exclude(snippet, parsed):
                continue
            
            # 文件类型过滤
            file_type = metadata.get('file_type', '').lstrip('.')
            if final_file_types and file_type not in final_file_types:
                continue
            
            doc_id = metadata.get('document_id', '') + '_' + str(metadata.get('chunk_index', 0))
            normalized_score = score / max_bm25 if max_bm25 > 0 else 0
            
            if doc_id in combined_results:
                combined_results[doc_id]['bm25_score'] = normalized_score
            else:
                combined_results[doc_id] = {
                    "document_id": metadata.get('document_id', ''),
                    "filename": metadata.get('filename', ''),
                    "path": metadata.get('filepath', ''),
                    "file_type": metadata.get('file_type', ''),
                    "vector_score": 0.0,
                    "bm25_score": normalized_score,
                    "content_snippet": snippet[:200] + "..." if len(snippet) > 200 else snippet,
                    "chunk_index": metadata.get('chunk_index', 0),
                    "full_content": snippet,
                    "has_exact_match": parser.has_exact_match(snippet, parsed)
                }
        
        # 5. 计算混合分数
        for doc_id, result in combined_results.items():
            result['similarity'] = alpha * result['vector_score'] + (1 - alpha) * result['bm25_score']
        
        # 6. 排序并限制数量（精确匹配优先）
        results = list(combined_results.values())
        results.sort(
            key=lambda x: (x.get('has_exact_match', False), x['similarity']),
            reverse=True
        )
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

        model_name = os.getenv('RERANK_MODEL', '../models/bge-reranker-base')
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
        client, collection = init_chroma_client()
        if not client or not collection:
            logger.error("初始化Chroma客户端失败")
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
        client, collection = init_chroma_client()
        if not client or not collection:
            logger.error("初始化Chroma客户端失败")
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
        client, collection = init_chroma_client()
        if not client or not collection:
            logger.error("初始化Chroma客户端失败")
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
        client, collection = init_chroma_client()
        if not client or not collection:
            logger.error("初始化Chroma客户端失败")
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