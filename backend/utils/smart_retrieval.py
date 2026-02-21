"""
智能检索模块 - 实现 Query Expansion + Multi-Query Retrieval + LLM Reranking
架构流程：
1. Query Expansion: 使用LLM扩展用户查询，生成相似词/同义词
2. Multi-Query Retrieval: 对扩展后的多个查询进行并行检索
3. Result Fusion: 合并多个查询的检索结果
4. LLM Reranking: 使用LLM对最终结果进行精确重排序
"""
import os
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

logger = logging.getLogger(__name__)

_llm_client = None

def _get_llm_client():
    """获取LLM客户端（兼容OpenAI API）"""
    global _llm_client
    if _llm_client is not None:
        return _llm_client

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai库未安装，智能检索功能不可用")
        return None

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")

    if not api_key:
        logger.warning("未配置 OPENAI_API_KEY 环境变量，智能检索功能不可用")
        return None

    try:
        _llm_client = OpenAI(api_key=api_key, base_url=base_url)
        logger.info(f"智能检索LLM客户端初始化成功: {base_url}, model={model}")
        return _llm_client
    except Exception as e:
        logger.error(f"LLM客户端初始化失败: {str(e)}")
        return None


def is_llm_available() -> bool:
    """检查LLM是否可用"""
    return _get_llm_client() is not None


def expand_query_with_llm(query: str, num_expansions: int = 5) -> List[str]:
    """
    使用LLM扩展查询，生成语义相似的查询词
    
    :param query: 原始查询
    :param num_expansions: 扩展查询数量
    :return: 扩展后的查询列表（包含原始查询）
    """
    client = _get_llm_client()
    if client is None:
        logger.warning("LLM不可用，返回原始查询")
        return [query]
    
    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    
    prompt = f"""你是一个专业的信息检索助手。用户输入了一个查询词，请生成{num_expansions}个语义相似或相关的查询词，用于扩大检索范围。

要求：
1. 包含同义词、近义词、相关概念
2. 包含中英文对照（如果适用）
3. 包含上下位概念（如"计算机"可以扩展为"电脑"、"计算设备"、"PC"等）
4. 包含专业术语和通俗表达
5. 每行一个查询词，不要编号和解释

原始查询：{query}

请生成{num_expansions}个扩展查询词："""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7
        )
        
        content = response.choices[0].message.content.strip()
        expansions = [line.strip() for line in content.split('\n') if line.strip()]
        
        expansions = [q for q in expansions if len(q) > 1 and len(q) < 50]
        
        expansions = list(dict.fromkeys(expansions))[:num_expansions]
        
        if query not in expansions:
            expansions.insert(0, query)
        
        logger.info(f"查询扩展成功: '{query}' -> {expansions}")
        return expansions
        
    except Exception as e:
        logger.error(f"查询扩展失败: {str(e)}")
        return [query]


def expand_query_keywords(query: str) -> List[str]:
    """
    使用关键词提取和同义词扩展（不依赖LLM的轻量级扩展）
    
    :param query: 原始查询
    :return: 扩展后的查询列表
    """
    expansions = [query]
    
    try:
        import jieba
        
        words = jieba.lcut(query)
        words = [w for w in words if len(w) > 1]
        
        synonyms = {
            '计算机': ['电脑', 'PC', '计算设备', '计算机器'],
            '电脑': ['计算机', 'PC', '笔记本', '台式机'],
            '手机': ['移动电话', '智能机', '移动设备', 'iPhone', '安卓'],
            '人工智能': ['AI', '机器智能', '智能计算', '深度学习'],
            '机器学习': ['ML', '深度学习', '神经网络', 'AI'],
            '数据库': ['DB', '数据存储', 'MySQL', '数据库系统'],
            '网络': ['互联网', '局域网', 'Internet', '网络通信'],
            '软件': ['程序', '应用', 'APP', '应用程序'],
            '硬件': ['设备', '机器', '物理设备'],
            '合同': ['协议', '契约', '合约'],
            '报告': ['汇报', '总结', '文档'],
            '计划': ['方案', '规划', '安排'],
            '项目': ['工程', '任务', '课题'],
            '会议': ['讨论', '会谈', '集会'],
            '培训': ['学习', '教育', '训练'],
            '财务': ['会计', '资金', '财务'],
            '人事': ['人力资源', 'HR', '员工'],
            '销售': ['营销', '售卖', '出售'],
            '技术': ['科技', '工艺', '方法'],
            '管理': ['治理', '管控', '经营'],
        }
        
        for word in words:
            if word in synonyms:
                expansions.extend(synonyms[word][:3])
        
        expansions = list(dict.fromkeys(expansions))
        
    except ImportError:
        logger.warning("jieba未安装，跳过关键词扩展")
    except Exception as e:
        logger.warning(f"关键词扩展失败: {str(e)}")
    
    return expansions[:6]


def multi_query_retrieval(queries: List[str], search_func, limit_per_query: int = 5) -> List[Dict]:
    """
    多查询检索：对多个查询进行并行检索并合并结果
    
    :param queries: 查询列表
    :param search_func: 检索函数
    :param limit_per_query: 每个查询返回的结果数
    :return: 合并后的检索结果
    """
    all_results = []
    doc_scores = Counter()
    doc_data = {}
    
    for i, q in enumerate(queries):
        try:
            results = search_func(q, limit=limit_per_query)
            for result in results:
                doc_id = result.get('document_id', '') + '_' + str(result.get('chunk_index', 0))
                
                weight = 1.0 / (i + 1)
                score = result.get('similarity', 0) * weight
                doc_scores[doc_id] += score
                
                if doc_id not in doc_data:
                    doc_data[doc_id] = result
                    doc_data[doc_id]['query_count'] = 1
                    doc_data[doc_id]['matched_queries'] = [q]
                else:
                    doc_data[doc_id]['query_count'] += 1
                    doc_data[doc_id]['matched_queries'].append(q)
                    
        except Exception as e:
            logger.warning(f"查询 '{q}' 检索失败: {str(e)}")
    
    ranked_docs = doc_scores.most_common()
    
    merged_results = []
    for doc_id, score in ranked_docs:
        result = doc_data[doc_id]
        result['merged_score'] = score
        result['multi_query_hit'] = result['query_count'] > 1
        merged_results.append(result)
    
    logger.info(f"多查询检索完成: {len(queries)}个查询 -> {len(merged_results)}条结果")
    return merged_results


def llm_rerank(query: str, results: List[Dict], top_k: int = 10) -> List[Dict]:
    """
    使用LLM对检索结果进行精确重排序
    
    :param query: 原始查询
    :param results: 检索结果列表
    :param top_k: 返回前k个结果
    :return: 重排序后的结果
    """
    if not results:
        return results
    
    client = _get_llm_client()
    if client is None:
        logger.warning("LLM不可用，使用原始排序")
        return results[:top_k]
    
    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    
    if len(results) > 15:
        results = results[:15]
    
    docs_text = ""
    for i, r in enumerate(results):
        snippet = r.get('content_snippet', '')[:300]
        docs_text += f"\n[文档{i+1}] 文件: {r.get('filename', '未知')}\n内容: {snippet}\n"
    
    prompt = f"""你是一个专业的信息检索评估专家。用户输入了一个查询，请对以下检索结果进行相关性评分。

用户查询：{query}

检索结果：
{docs_text}

请对每个文档与查询的相关性进行评分（0-10分），评分标准：
- 10分：完全匹配，直接回答了查询
- 7-9分：高度相关，包含关键信息
- 4-6分：部分相关，包含一些相关信息
- 1-3分：低相关，只有少量相关信息
- 0分：不相关

请直接返回评分结果，格式为：文档编号:分数，每行一个。例如：
1:9
2:7
3:5

请开始评分："""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1
        )
        
        content = response.choices[0].message.content.strip()
        
        scores = {}
        for line in content.split('\n'):
            line = line.strip()
            if ':' in line or '：' in line:
                parts = line.replace('：', ':').split(':')
                if len(parts) >= 2:
                    try:
                        doc_idx = int(parts[0].strip())
                        score = float(parts[1].strip())
                        if 1 <= doc_idx <= len(results):
                            scores[doc_idx - 1] = min(10, max(0, score))
                    except ValueError:
                        continue
        
        for i, result in enumerate(results):
            llm_score = scores.get(i, 5)
            result['llm_score'] = llm_score
            result['original_similarity'] = result.get('similarity', 0)
            result['similarity'] = llm_score / 10.0
            result['rerank_method'] = 'llm'
        
        results.sort(key=lambda x: x.get('llm_score', 0), reverse=True)
        
        logger.info(f"LLM重排序完成: {len(results)}条结果")
        return results[:top_k]
        
    except Exception as e:
        logger.error(f"LLM重排序失败: {str(e)}")
        return results[:top_k]


def smart_retrieval(
    query: str,
    search_func,
    limit: int = 10,
    use_query_expansion: bool = True,
    use_llm_rerank: bool = True,
    expansion_method: str = 'llm'
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    智能检索：完整的 Query Expansion + Multi-Query Retrieval + LLM Reranking 流程
    
    :param query: 用户查询
    :param search_func: 检索函数
    :param limit: 返回结果数量
    :param use_query_expansion: 是否使用查询扩展
    :param use_llm_rerank: 是否使用LLM重排序
    :param expansion_method: 扩展方法 ('llm' 或 'keyword')
    :return: (检索结果, 检索元信息)
    """
    meta_info = {
        'original_query': query,
        'expanded_queries': [query],
        'expansion_method': None,
        'rerank_method': None,
        'total_candidates': 0
    }
    
    if use_query_expansion:
        if expansion_method == 'llm' and is_llm_available():
            queries = expand_query_with_llm(query)
            meta_info['expansion_method'] = 'llm'
        else:
            queries = expand_query_keywords(query)
            meta_info['expansion_method'] = 'keyword'
        
        meta_info['expanded_queries'] = queries
        
        results = multi_query_retrieval(queries, search_func, limit_per_query=max(3, limit // 2))
    else:
        results = search_func(query, limit=limit * 2)
    
    meta_info['total_candidates'] = len(results)
    
    if use_llm_rerank and is_llm_available() and results:
        results = llm_rerank(query, results, top_k=limit)
        meta_info['rerank_method'] = 'llm'
    else:
        results = results[:limit]
    
    for result in results:
        result.pop('query_count', None)
        result.pop('matched_queries', None)
        result.pop('merged_score', None)
    
    logger.info(f"智能检索完成: query='{query}', expansions={len(meta_info['expanded_queries'])}, results={len(results)}")
    
    return results, meta_info
