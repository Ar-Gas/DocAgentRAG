"""RRF fusion - 互倒序排名融合"""
from typing import List, Dict, Any, Optional


def _result_document_id(hit: Dict[str, Any]) -> Optional[str]:
    return hit.get("document_id") or hit.get("doc_id") or hit.get("id")


def reciprocal_rank_fusion(
    vector_hits: List[Dict[str, Any]],
    bm25_hits: List[Dict[str, Any]],
    graph_hits: Optional[List[Dict[str, Any]]] = None,
    weights: Optional[Dict[str, float]] = None
) -> List[Dict[str, Any]]:
    """
    互倒序排名（RRF）融合多路检索结果

    Args:
        vector_hits: 向量检索结果（需要有 score 字段）
        bm25_hits: BM25 检索结果
        graph_hits: 图检索结果（可选）
        weights: 权重配置 {"vector": 0.4, "bm25": 0.4, "graph": 0.2}

    Returns:
        融合后的结果列表，按综合分数排序
    """
    if weights is None:
        weights = {"vector": 0.4, "bm25": 0.4, "graph": 0.2}

    # 将各路结果转换为 doc_id -> score 的字典
    rrf_scores: Dict[str, float] = {}

    # 向量检索：使用倒数排名
    for i, hit in enumerate(vector_hits):
        doc_id = _result_document_id(hit)
        if not doc_id:
            continue
        rrf_scores.setdefault(doc_id, 0)
        rrf_scores[doc_id] += weights["vector"] / (i + 1)

    # BM25 检索
    for i, hit in enumerate(bm25_hits):
        doc_id = _result_document_id(hit)
        if not doc_id:
            continue
        rrf_scores.setdefault(doc_id, 0)
        rrf_scores[doc_id] += weights["bm25"] / (i + 1)

    # 图检索（如果有）
    if graph_hits:
        for i, hit in enumerate(graph_hits):
            doc_id = _result_document_id(hit)
            if not doc_id:
                continue
            rrf_scores.setdefault(doc_id, 0)
            rrf_scores[doc_id] += weights["graph"] / (i + 1)

    # 按分数排序
    sorted_results = sorted(
        rrf_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    # 构造输出
    fused_results = []
    for doc_id, score in sorted_results:
        # 找到原始 hit 以保留其他信息
        original_hit = None
        for hits in [vector_hits, bm25_hits] + ([graph_hits] if graph_hits else []):
            if hits:
                for hit in hits:
                    if _result_document_id(hit) == doc_id:
                        original_hit = hit
                        break
            if original_hit:
                break

        fused_result = original_hit.copy() if original_hit else {"document_id": doc_id}
        if "document_id" not in fused_result and doc_id:
            fused_result["document_id"] = doc_id
        fused_result["_fusion_score"] = score
        fused_results.append(fused_result)

    return fused_results
