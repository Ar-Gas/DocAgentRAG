import os
import re
import math
import base64
import json
from collections import Counter
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

from app.core.logger import logger
from app.infra.embedding_provider import doubao_multimodal_embed, get_local_embedding_model_name
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.vector_store import get_block_collection
from config import DATA_DIR


def get_all_documents():
    return DocumentRepository(data_dir=DATA_DIR).list_all()


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


def _normalize_file_type_filters(file_types: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    for item in file_types or []:
        value = (item or "").strip().lower().lstrip(".")
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _merge_file_type_filters(
    file_types: Optional[List[str]],
    query_file_types: Optional[List[str]],
) -> List[str]:
    merged: List[str] = []
    for item in [*(file_types or []), *(query_file_types or [])]:
        value = (item or "").strip().lower().lstrip(".")
        if value and value not in merged:
            merged.append(value)
    return merged


def _normalize_block_payload_results(
    block_payload: Dict[str, Any],
    parsed_query: Optional[ParsedQuery] = None,
) -> List[Dict[str, Any]]:
    document_lookup = {
        document.get("document_id"): document
        for document in block_payload.get("documents") or []
        if document.get("document_id")
    }
    normalized_results: List[Dict[str, Any]] = []

    for item in block_payload.get("results") or []:
        document = document_lookup.get(item.get("document_id"), {})
        snippet = item.get("content_snippet") or item.get("snippet") or document.get("best_excerpt") or document.get("preview_content", "")
        result = {
            "document_id": item.get("document_id"),
            "filename": item.get("filename") or document.get("filename", ""),
            "path": item.get("path") or document.get("path", ""),
            "file_type": item.get("file_type") or document.get("file_type", ""),
            "similarity": round(float(item.get("similarity", item.get("score", 0.0)) or 0.0), 4),
            "content_snippet": snippet,
            "chunk_index": item.get("chunk_index", item.get("block_index", 0)),
            "block_id": item.get("block_id"),
            "block_index": item.get("block_index", item.get("chunk_index", 0)),
            "block_type": item.get("block_type", "paragraph"),
            "heading_path": item.get("heading_path", []),
            "page_number": item.get("page_number"),
            "classification_result": item.get("classification_result", document.get("classification_result")),
            "created_at_iso": item.get("created_at_iso", document.get("created_at_iso")),
            "parser_name": item.get("parser_name", document.get("parser_name")),
            "extraction_status": item.get("extraction_status", document.get("extraction_status")),
            "preview_content": item.get("preview_content", document.get("preview_content", "")),
            "file_available": item.get("file_available", document.get("file_available", False)),
            "match_reason": item.get("match_reason", ""),
        }
        if parsed_query is not None:
            result["has_exact_match"] = _query_parser.has_exact_match(snippet, parsed_query)
        normalized_results.append(result)

    return normalized_results


def _filter_advanced_query_results(
    results: List[Dict[str, Any]],
    parsed_query: Optional[ParsedQuery],
) -> List[Dict[str, Any]]:
    if parsed_query is None:
        return results

    filtered: List[Dict[str, Any]] = []
    for result in results:
        snippet = result.get("content_snippet", "")
        if _query_parser.should_exclude(snippet, parsed_query):
            continue
        result["has_exact_match"] = _query_parser.has_exact_match(snippet, parsed_query)
        filtered.append(result)
    return filtered


def _sort_legacy_results(
    results: List[Dict[str, Any]],
    *,
    prefer_exact_match: bool = False,
) -> List[Dict[str, Any]]:
    if prefer_exact_match:
        results.sort(
            key=lambda item: (item.get("has_exact_match", False), item.get("similarity", 0.0)),
            reverse=True,
        )
    else:
        results.sort(key=lambda item: item.get("similarity", 0.0), reverse=True)
    return results


def _search_via_block_payload(
    query: str,
    *,
    mode: str,
    limit: int,
    alpha: float,
    file_types: Optional[List[str]],
    parsed_query: Optional[ParsedQuery] = None,
) -> List[Dict[str, Any]]:
    normalized_file_types = _normalize_file_type_filters(file_types)
    ready_document_ids = get_ready_block_document_ids(
        file_types=normalized_file_types,
        filename=None,
        classification=None,
        date_from=None,
        date_to=None,
    )
    if not ready_document_ids:
        return []

    block_payload = search_block_documents(
        query=query,
        mode=mode,
        limit=limit,
        alpha=alpha,
        use_rerank=False,
        use_llm_rerank=False,
        file_types=normalized_file_types,
        classification=None,
        date_from=None,
        date_to=None,
        ready_document_ids=ready_document_ids,
        group_by_document=False,
    )
    results = _normalize_block_payload_results(block_payload, parsed_query=parsed_query)
    return _filter_advanced_query_results(results, parsed_query)


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

    parsed = _query_parser.parse(query)
    final_file_types = _merge_file_type_filters(file_types, parsed.file_types)
    search_query = _query_parser.get_search_string(parsed).strip() or parsed.original_query

    try:
        search_results = _search_via_block_payload(
            search_query,
            mode="keyword",
            limit=limit,
            alpha=0.0,
            file_types=final_file_types,
            parsed_query=parsed,
        )
        search_results = _sort_legacy_results(search_results, prefer_exact_match=True)[:limit]
        logger.info(f"关键词检索完成: query='{query[:50]}...', results={len(search_results)}")
        return search_results
    except Exception as exc:
        logger.error(f"关键词检索失败: {str(exc)}")
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
        collection = get_block_collection()
        if collection is None:
            logger.error("document_blocks collection 不可用")
            return []

        query_embedding = get_query_embedding(query, image_url, image_path)
        if query_embedding is None:
            logger.warning("豆包嵌入失败，回退到文本检索")
            return search_documents(query, limit=limit, file_types=file_types)

        normalized_file_types = _normalize_file_type_filters(file_types)
        ready_document_ids = get_ready_block_document_ids(
            file_types=normalized_file_types,
            filename=None,
            classification=None,
            date_from=None,
            date_to=None,
        )
        if not ready_document_ids:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=max(limit * 5, 10),
            include=["documents", "metadatas", "distances"],
        )

        document_lookup = {
            document.get("id"): document
            for document in get_all_documents()
            if document.get("id") in ready_document_ids
        }
        candidates: Dict[str, Dict[str, Any]] = {}
        for item in _flatten_query_results(results):
            metadata = item.get("metadata") or {}
            document_id = metadata.get("document_id")
            if document_id not in ready_document_ids:
                continue
            candidate = _upsert_block_candidate(
                candidates,
                {
                    "id": metadata.get("block_id"),
                    "document": item.get("document") or "",
                    "metadata": metadata,
                },
                document_lookup,
            )
            if candidate is None:
                continue
            score = max(0.0, min(1.0, 1 - float(item.get("distance", 1.0) or 1.0)))
            candidate["score"] = max(candidate.get("score", 0.0), score)

        search_results = [
            {
                "document_id": candidate.get("document_id"),
                "filename": candidate.get("filename", ""),
                "path": candidate.get("path", ""),
                "file_type": candidate.get("file_type", ""),
                "similarity": round(float(candidate.get("score", 0.0) or 0.0), 4),
                "content_snippet": candidate.get("snippet", ""),
                "chunk_index": candidate.get("block_index", 0),
                "block_id": candidate.get("block_id"),
                "block_index": candidate.get("block_index", 0),
                "embedding_model": get_local_embedding_model_name(),
                "multimodal_query": bool(image_url or image_path),
            }
            for candidate in candidates.values()
            if candidate.get("score", 0.0) > 0
        ]
        search_results.sort(
            key=lambda item: (
                item.get("similarity", 0.0),
                -item.get("block_index", 0),
            ),
            reverse=True,
        )
        search_results = search_results[:limit]

        logger.info(f"多模态检索完成: query='{query[:50]}...', has_image={bool(image_url or image_path)}, results={len(search_results)}")
        return search_results

    except Exception as exc:
        logger.error(f"多模态检索失败: {str(exc)}")
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

    parsed = _query_parser.parse(query)
    final_file_types = _merge_file_type_filters(file_types, parsed.file_types)
    search_query = _query_parser.get_search_string(parsed).strip() or parsed.original_query

    try:
        results = _search_via_block_payload(
            search_query,
            mode="hybrid",
            limit=limit,
            alpha=alpha,
            file_types=final_file_types,
            parsed_query=parsed,
        )
        results = _sort_legacy_results(results, prefer_exact_match=True)
        if use_rerank and results:
            results = rerank_documents(query, results, top_k=limit)
        else:
            results = results[:limit]
        logger.info(f"混合检索完成: 向量权重={alpha}, 返回{len(results)}条结果")
        return results
    except Exception as exc:
        logger.error(f"混合检索失败: {str(exc)}")
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
    if not query or not isinstance(query, str) or limit <= 0:
        logger.error("搜索失败：查询为空或结果数非法")
        return []

    try:
        search_results = _search_via_block_payload(
            query,
            mode="vector",
            limit=limit,
            alpha=1.0,
            file_types=file_types,
        )
        search_results = _sort_legacy_results(search_results)[:limit]
        if use_rerank and search_results:
            search_results = rerank_documents(query, search_results, top_k=limit)

        logger.info(f"搜索完成，返回 {len(search_results)} 条结果")
        return search_results
    except Exception as exc:
        logger.error(f"搜索文档失败: {str(exc)}")
        return []

# 批量搜索文档（支持多查询）
def batch_search_documents(queries, limit=5):
    """
    批量搜索多个查询
    :param queries: 查询文本列表
    :param limit: 每个查询返回结果数量限制
    :return: 每个查询的搜索结果列表
    """
    if not isinstance(queries, list) or len(queries) == 0 or limit <= 0:
        logger.error("批量搜索失败：查询列表为空或结果数非法")
        return []

    batch_results = []
    for query in queries:
        try:
            batch_results.append(search_documents(query, limit=limit, use_rerank=False, file_types=None))
        except Exception as exc:
            logger.error(f"批量搜索文档失败: {str(exc)}")
            batch_results.append([])

    logger.info(f"批量搜索完成，处理 {len(batch_results)} 条查询")
    return batch_results

# 根据文档ID获取文档信息
def get_document_by_id(document_id):
    """
    根据文档ID获取文档信息
    :param document_id: 文档ID
    :return: 文档信息
    """
    if not document_id or not isinstance(document_id, str):
        logger.error("根据ID获取文档失败：文档ID为空或非法")
        return None

    try:
        collection = get_block_collection()
        if collection is None:
            logger.error("document_blocks collection 不可用")
            return None

        results = collection.get(where={"document_id": document_id}, include=["documents", "metadatas"])
        ids = list(results.get("ids") or [])
        documents = list(results.get("documents") or [])
        metadatas = list(results.get("metadatas") or [])
        if not ids:
            return None

        if len(documents) < len(ids):
            documents.extend([""] * (len(ids) - len(documents)))
        if len(metadatas) < len(ids):
            metadatas.extend([{}] * (len(ids) - len(metadatas)))

        rows = []
        for index, row_id in enumerate(ids):
            metadata = dict(metadatas[index] or {})
            block_index = int(metadata.get("block_index", metadata.get("chunk_index", 0)) or 0)
            metadata.setdefault("chunk_index", block_index)
            rows.append((block_index, row_id, documents[index] or "", metadata))

        rows.sort(key=lambda item: item[0])
        logger.info(f"根据ID获取文档成功：{document_id}，共 {len(rows)} 个分块")
        return {
            "chunks": [item[2] for item in rows],
            "metadatas": [item[3] for item in rows],
            "ids": [item[1] for item in rows],
        }
    except Exception as exc:
        logger.error(f"根据ID获取文档失败: {str(exc)}")
        return None


_FILE_TYPE_FAMILY_MAP = {
    "pdf": "pdf",
    "doc": "word",
    "docx": "word",
    "word": "word",
    "ppt": "ppt",
    "pptx": "ppt",
    "presentation": "ppt",
    "xls": "excel",
    "xlsx": "excel",
    "csv": "excel",
    "excel": "excel",
    "eml": "eml",
    "msg": "eml",
    "txt": "txt",
    "md": "txt",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "bmp": "image",
    "image": "image",
}


def _normalize_filter_file_type(value: Optional[str]) -> str:
    return (value or "").strip().lower().lstrip(".")


def _derive_file_type_family(file_type: Optional[str]) -> str:
    normalized = _normalize_filter_file_type(file_type)
    return _FILE_TYPE_FAMILY_MAP.get(normalized, normalized)


def _parse_filter_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(f"{normalized}T00:00:00")
        except ValueError:
            return None


def _is_on_or_after(value: Optional[str], lower_bound: Optional[str]) -> bool:
    created_at = _parse_filter_datetime(value)
    lower = _parse_filter_datetime(lower_bound)
    if created_at is None or lower is None:
        return False
    return created_at >= lower


def _is_on_or_before(value: Optional[str], upper_bound: Optional[str]) -> bool:
    created_at = _parse_filter_datetime(value)
    upper = _parse_filter_datetime(upper_bound)
    if created_at is None or upper is None:
        return False
    if len(str(upper_bound).strip()) == 10:
        upper = upper.replace(hour=23, minute=59, second=59, microsecond=999999)
    return created_at <= upper


def _matches_block_document_filters(
    document: Dict[str, Any],
    file_types: Optional[List[str]] = None,
    filename: Optional[str] = None,
    classification: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> bool:
    normalized_file_types = [_normalize_filter_file_type(item) for item in (file_types or []) if item]
    document_file_type = _normalize_filter_file_type(document.get("file_type"))
    document_family = _normalize_filter_file_type(
        document.get("file_type_family") or _derive_file_type_family(document.get("file_type"))
    )

    if normalized_file_types and document_file_type not in normalized_file_types and document_family not in normalized_file_types:
        return False

    if filename and filename.strip().lower() not in (document.get("filename") or "").lower():
        return False

    if classification:
        normalized_filter = classification.strip().lower()
        classification_id = (document.get("classification_id") or "").strip().lower()
        document_classification = (document.get("classification_result") or "未分类").lower()
        classification_path = str(document.get("classification_path") or "").lower()
        if (
            normalized_filter != classification_id
            and normalized_filter not in document_classification
            and normalized_filter not in classification_path
        ):
            return False

    created_at = document.get("created_at_iso")
    if date_from and not _is_on_or_after(created_at, date_from):
        return False
    if date_to and not _is_on_or_before(created_at, date_to):
        return False

    return True


def get_ready_block_document_ids(
    file_types: Optional[List[str]] = None,
    filename: Optional[str] = None,
    classification: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> set[str]:
    ready_ids: set[str] = set()
    for document in get_all_documents():
        document_id = document.get("id")
        if not document_id:
            continue
        if (document.get("block_index_status") or "").strip().lower() != "ready":
            continue
        if not _matches_block_document_filters(
            document,
            file_types=file_types,
            filename=filename,
            classification=classification,
            date_from=date_from,
            date_to=date_to,
        ):
            continue
        ready_ids.add(document_id)
    return ready_ids


def _parse_heading_path(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
        return [segment.strip() for segment in value.split(">") if segment.strip()]
    return []


def _coerce_page_number(value: Any) -> Optional[int]:
    try:
        page_number = int(value)
    except (TypeError, ValueError):
        return None
    return page_number if page_number >= 0 else None


def _build_block_search_text(row: Dict[str, Any]) -> str:
    metadata = row.get("metadata") or {}
    parts = [
        " ".join(_parse_heading_path(metadata.get("heading_path"))),
        row.get("document") or "",
    ]
    return "\n".join(part for part in parts if part).strip()


def _load_block_rows_for_documents(collection, ready_document_ids: set[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for document_id in ready_document_ids:
        try:
            response = collection.get(where={"document_id": document_id}, include=["documents", "metadatas"])
        except Exception:
            continue

        ids = list(response.get("ids") or [])
        documents = list(response.get("documents") or [])
        metadatas = list(response.get("metadatas") or [])

        if len(documents) < len(ids):
            documents.extend([""] * (len(ids) - len(documents)))
        if len(metadatas) < len(ids):
            metadatas.extend([{}] * (len(ids) - len(metadatas)))

        for index, row_id in enumerate(ids):
            rows.append(
                {
                    "id": row_id,
                    "document": documents[index] or "",
                    "metadata": metadatas[index] or {},
                }
            )
    return rows


def _upsert_block_candidate(
    candidates: Dict[str, Dict[str, Any]],
    row: Dict[str, Any],
    document_lookup: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    metadata = row.get("metadata") or {}
    document_id = metadata.get("document_id")
    if not document_id:
        return None

    block_id = metadata.get("block_id") or row.get("id")
    if not block_id:
        return None

    snippet = row.get("document") or ""
    document_info = document_lookup.get(document_id, {})
    candidate = candidates.setdefault(
        block_id,
        {
            "document_id": document_id,
            "block_id": block_id,
            "block_index": int(metadata.get("block_index", 0) or 0),
            "snippet": snippet[:240],
            "raw_text": snippet,
            "filename": metadata.get("filename") or document_info.get("filename", ""),
            "path": document_info.get("filepath") or metadata.get("filepath", ""),
            "file_type": metadata.get("file_type") or document_info.get("file_type", ""),
            "classification_result": document_info.get("classification_result"),
            "file_available": document_info.get("file_available", False),
            "created_at_iso": document_info.get("created_at_iso"),
            "parser_name": document_info.get("parser_name"),
            "extraction_status": document_info.get("extraction_status"),
            "preview_content": document_info.get("preview_content") or snippet[:240],
            "block_type": metadata.get("block_type", "paragraph"),
            "heading_path": _parse_heading_path(metadata.get("heading_path")),
            "page_number": _coerce_page_number(metadata.get("page_number")),
            "vector_score": 0.0,
            "bm25_score": 0.0,
            "score": 0.0,
            "match_reason": "",
        },
    )
    if len(snippet) > len(candidate.get("raw_text") or ""):
        candidate["raw_text"] = snippet
        candidate["snippet"] = snippet[:240]
    return candidate


def _build_block_match_reason(
    heading_path: List[str],
    snippet: str,
    search_terms: List[str],
    mode: str,
) -> str:
    heading_text = " ".join(heading_path or []).lower()
    body_text = (snippet or "").lower()
    heading_match = any(term in heading_text for term in search_terms if term)
    body_match = any(term in body_text for term in search_terms if term)
    if heading_match and body_match:
        return "heading + body match"
    if heading_match:
        return "heading match"
    if body_match:
        return "body match"
    return "vector match" if mode == "vector" else "keyword match"


def _flatten_query_results(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    metadatas = results.get("metadatas") or []
    documents = results.get("documents") or []
    distances = results.get("distances") or []

    if metadatas and not isinstance(metadatas[0], list):
        metadatas = [metadatas]
        documents = [documents]
        distances = [distances]

    for index in range(len(metadatas)):
        metadata_items = metadatas[index] or []
        document_items = documents[index] or []
        distance_items = distances[index] or []
        min_len = min(len(metadata_items), len(document_items), len(distance_items))
        for item_index in range(min_len):
            flattened.append(
                {
                    "metadata": metadata_items[item_index] or {},
                    "document": document_items[item_index] or "",
                    "distance": distance_items[item_index],
                }
            )
    return flattened


def search_block_documents(
    query: str,
    mode: str,
    limit: int,
    alpha: float,
    use_rerank: bool,
    use_llm_rerank: bool,
    file_types: Optional[List[str]],
    classification: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    ready_document_ids: set[str],
    group_by_document: bool = True,
    use_query_expansion: bool = True,
    expansion_method: str = "llm",
) -> Dict[str, Any]:
    collection = get_block_collection()
    if collection is None or not ready_document_ids:
        return {"documents": [], "results": [], "meta": {"fallback_used": False}}

    document_lookup = {
        document.get("id"): document
        for document in get_all_documents()
        if document.get("id") in ready_document_ids
    }
    block_rows = _load_block_rows_for_documents(collection, ready_document_ids)
    if not block_rows:
        return {"documents": [], "results": [], "meta": {"fallback_used": False}}

    normalized_mode = (mode or "hybrid").strip().lower()
    parser = get_query_parser()
    parsed = parser.parse(query) if query else parser.parse("")
    search_terms: List[str] = []
    for item in [*parsed.include_terms, *parsed.exact_phrases, *parsed.fuzzy_terms]:
        normalized = (item or "").strip().lower()
        if normalized and normalized not in search_terms:
            search_terms.append(normalized)
    normalized_query = (query or "").strip().lower()
    if normalized_query and normalized_query not in search_terms:
        search_terms.append(normalized_query)

    expanded_queries = [query] if query else []
    keyword_query = query
    if normalized_mode == "smart" and query and use_query_expansion:
        try:
            from .smart_retrieval import expand_query_keywords, expand_query_with_llm, is_llm_available

            if expansion_method == "llm" and is_llm_available():
                extra_queries = expand_query_with_llm(query)
            else:
                extra_queries = expand_query_keywords(query)
            for item in extra_queries:
                normalized = (item or "").strip()
                if normalized and normalized not in expanded_queries:
                    expanded_queries.append(normalized)
            keyword_query = " ".join(expanded_queries)
        except Exception:
            expanded_queries = [query]
            keyword_query = query

    candidates: Dict[str, Dict[str, Any]] = {}
    candidate_limit = min(max(limit * 8, 40), 200)

    if keyword_query and normalized_mode in {"keyword", "hybrid", "smart"}:
        corpus = [_build_block_search_text(row) for row in block_rows]
        bm25 = BM25()
        bm25.fit(corpus)
        bm25_scores = bm25.search(keyword_query, corpus, top_k=min(len(corpus), candidate_limit))
        max_bm25 = max((score for _, score in bm25_scores), default=0.0) or 1.0
        for index, score in bm25_scores:
            row = block_rows[index]
            candidate = _upsert_block_candidate(candidates, row, document_lookup)
            if candidate is None:
                continue
            candidate["bm25_score"] = max(candidate["bm25_score"], score / max_bm25)

    if query and normalized_mode in {"vector", "hybrid", "smart"}:
        for search_query in expanded_queries or [query]:
            try:
                query_results = collection.query(
                    query_texts=[search_query],
                    n_results=candidate_limit,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception:
                query_results = {}

            for item in _flatten_query_results(query_results):
                metadata = item.get("metadata") or {}
                document_id = metadata.get("document_id")
                if document_id not in ready_document_ids:
                    continue
                row = {
                    "id": metadata.get("block_id"),
                    "document": item.get("document") or "",
                    "metadata": metadata,
                }
                candidate = _upsert_block_candidate(candidates, row, document_lookup)
                if candidate is None:
                    continue
                vector_score = max(0.0, min(1.0, 1 - float(item.get("distance", 1.0) or 1.0)))
                candidate["vector_score"] = max(candidate["vector_score"], vector_score)

    flat_results: List[Dict[str, Any]] = []
    if not query:
        for row in block_rows:
            candidate = _upsert_block_candidate(candidates, row, document_lookup)
            if candidate is None:
                continue
            candidate["score"] = 1.0

    for candidate in candidates.values():
        if query:
            if normalized_mode == "keyword":
                candidate["score"] = candidate["bm25_score"]
            elif normalized_mode == "vector":
                candidate["score"] = candidate["vector_score"]
            else:
                candidate["score"] = alpha * candidate["vector_score"] + (1 - alpha) * candidate["bm25_score"]
            if candidate["score"] <= 0:
                continue
        candidate["score"] = round(candidate["score"], 4)
        candidate["match_reason"] = _build_block_match_reason(
            candidate.get("heading_path") or [],
            candidate.get("raw_text") or candidate.get("snippet", ""),
            search_terms,
            normalized_mode,
        )
        flat_results.append(
            {
                "document_id": candidate.get("document_id"),
                "filename": candidate.get("filename", ""),
                "file_type": candidate.get("file_type", ""),
                "path": candidate.get("path", ""),
                "classification_result": candidate.get("classification_result"),
                "file_available": candidate.get("file_available", False),
                "created_at_iso": candidate.get("created_at_iso"),
                "parser_name": candidate.get("parser_name"),
                "extraction_status": candidate.get("extraction_status"),
                "preview_content": candidate.get("preview_content", ""),
                "block_id": candidate.get("block_id"),
                "block_index": candidate.get("block_index", 0),
                "block_type": candidate.get("block_type", "paragraph"),
                "snippet": candidate.get("snippet", ""),
                "heading_path": candidate.get("heading_path") or [],
                "page_number": candidate.get("page_number"),
                "score": candidate.get("score", 0.0),
                "match_reason": candidate.get("match_reason", ""),
                "content_snippet": candidate.get("snippet", ""),
            }
        )

    flat_results.sort(
        key=lambda item: (
            item.get("score", 0.0),
            -item.get("block_index", 0),
        ),
        reverse=True,
    )

    if query and use_rerank and use_llm_rerank and len(flat_results) > 1:
        try:
            from .smart_retrieval import llm_rerank

            reranked = llm_rerank(
                query,
                [
                    {
                        **item,
                        "similarity": item.get("score", 0.0),
                        "content_snippet": item.get("snippet", ""),
                    }
                    for item in flat_results
                ],
                top_k=len(flat_results),
            )
            flat_results = [
                {
                    **item,
                    "score": round(float(item.get("similarity", item.get("score", 0.0)) or 0.0), 4),
                }
                for item in reranked
            ]
            flat_results.sort(
                key=lambda item: (
                    item.get("score", 0.0),
                    -item.get("block_index", 0),
                ),
                reverse=True,
            )
        except Exception:
            pass

    grouped_documents: Dict[str, Dict[str, Any]] = {}
    for result in flat_results:
        document_id = result.get("document_id")
        if not document_id:
            continue
        group = grouped_documents.setdefault(
            document_id,
            {
                "document_id": document_id,
                "filename": result.get("filename", ""),
                "file_type": result.get("file_type", ""),
                "path": result.get("path", ""),
                "classification_result": result.get("classification_result"),
                "created_at_iso": result.get("created_at_iso"),
                "parser_name": result.get("parser_name"),
                "extraction_status": result.get("extraction_status"),
                "preview_content": result.get("preview_content", ""),
                "score": result.get("score", 0.0),
                "best_similarity": result.get("score", 0.0),
                "hit_count": 0,
                "result_count": 0,
                "best_excerpt": "",
                "best_block_id": None,
                "matched_terms": list(search_terms),
                "file_available": result.get("file_available", False),
                "evidence_blocks": [],
                "top_segments": [],
                "results": [],
            },
        )
        group["hit_count"] += 1
        group["result_count"] = group["hit_count"]
        group["score"] = max(group["score"], result.get("score", 0.0))
        group["best_similarity"] = group["score"]
        group["results"].append(result)

        evidence_block = {
            "block_id": result.get("block_id"),
            "block_index": result.get("block_index", 0),
            "block_type": result.get("block_type", "paragraph"),
            "snippet": result.get("snippet", ""),
            "heading_path": result.get("heading_path") or [],
            "page_number": result.get("page_number"),
            "score": result.get("score", 0.0),
            "match_reason": result.get("match_reason", ""),
        }
        if evidence_block["block_id"] not in {item.get("block_id") for item in group["evidence_blocks"]}:
            group["evidence_blocks"].append(evidence_block)

        if not group["best_block_id"]:
            group["best_block_id"] = result.get("block_id")
            group["best_excerpt"] = result.get("snippet", "")

    documents = list(grouped_documents.values())
    for document in documents:
        document["evidence_blocks"] = sorted(
            document["evidence_blocks"],
            key=lambda item: (item.get("score", 0.0), -item.get("block_index", 0)),
            reverse=True,
        )[:3]
        document["results"] = sorted(
            document["results"],
            key=lambda item: (item.get("score", 0.0), -item.get("block_index", 0)),
            reverse=True,
        )
        if not document["best_block_id"] and document["evidence_blocks"]:
            document["best_block_id"] = document["evidence_blocks"][0].get("block_id")
        if not document["best_excerpt"] and document["evidence_blocks"]:
            document["best_excerpt"] = document["evidence_blocks"][0].get("snippet", "")

    documents.sort(
        key=lambda item: (
            item.get("score", 0.0),
            item.get("hit_count", 0),
            item.get("created_at_iso") or "",
        ),
        reverse=True,
    )

    if group_by_document:
        documents = documents[:limit]
        results = [
            {
                "document_id": document.get("document_id"),
                "block_id": evidence.get("block_id"),
                "block_index": evidence.get("block_index", 0),
                "snippet": evidence.get("snippet", ""),
                "score": evidence.get("score", 0.0),
                "match_reason": evidence.get("match_reason", ""),
            }
            for document in documents
            for evidence in document.get("evidence_blocks") or []
        ]
    else:
        results = [
            {
                "document_id": item.get("document_id"),
                "block_id": item.get("block_id"),
                "block_index": item.get("block_index", 0),
                "snippet": item.get("snippet", ""),
                "score": item.get("score", 0.0),
                "match_reason": item.get("match_reason", ""),
            }
            for item in flat_results[:limit]
        ]

    results.sort(
        key=lambda item: (
            item.get("score", 0.0),
            -item.get("block_index", 0),
        ),
        reverse=True,
    )
    return {
        "documents": documents,
        "results": results,
        "meta": {
            "fallback_used": False,
            "candidate_count": len(flat_results),
            "expanded_queries": expanded_queries,
        },
    }

# 获取文档统计信息
def get_document_stats():
    """
    获取文档统计信息（优化内存占用）
    :return: 统计信息
    """
    try:
        collection = get_block_collection()
        if collection is None:
            logger.error("document_blocks collection 不可用")
            return {"total_chunks": 0, "vector_indexed_documents": 0, "file_types": {}}

        total_chunks = collection.count()
        file_types: Dict[str, int] = {}
        document_ids: set[str] = set()

        if total_chunks > 0:
            batch_size = 1000
            for offset in range(0, total_chunks, batch_size):
                results = collection.get(limit=batch_size, offset=offset, include=["metadatas"])
                for metadata in results.get("metadatas") or []:
                    if metadata is None:
                        continue
                    document_id = metadata.get("document_id")
                    if document_id:
                        document_ids.add(document_id)
                    file_type = metadata.get("file_type")
                    if file_type:
                        file_types[file_type] = file_types.get(file_type, 0) + 1

        stats = {
            "total_chunks": total_chunks,
            "vector_indexed_documents": len(document_ids),
            "file_types": file_types,
        }
        logger.info(f"获取统计信息成功：{stats}")
        return stats
    except Exception as exc:
        logger.error(f"获取文档统计信息失败: {str(exc)}")
        return {"total_chunks": 0, "vector_indexed_documents": 0, "file_types": {}}
