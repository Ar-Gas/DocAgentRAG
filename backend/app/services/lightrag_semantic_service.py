from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.infra.lightrag_client import LightRAGClient


class LightRAGSemanticService:
    """Shared adapter for reading semantic artifacts from LightRAG."""

    def __init__(self, lightrag_client: LightRAGClient | None = None):
        self.lightrag_client = lightrag_client or LightRAGClient()

    @staticmethod
    def _normalize_file_path(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        return raw.replace("\\", "/")

    @staticmethod
    def _normalize_doc_key(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        path = Path(raw)
        return path.name or raw

    def _matches_document(self, candidate: Dict[str, Any], doc_info: Dict[str, Any]) -> bool:
        candidate_path = self._normalize_file_path(candidate.get("file_path"))
        candidate_name = self._normalize_doc_key(candidate_path or candidate.get("file_name") or candidate.get("doc_id"))
        expected_name = self._normalize_doc_key(doc_info.get("filename"))
        expected_path = self._normalize_file_path(doc_info.get("filepath"))

        if candidate_path and expected_path and candidate_path == expected_path:
            return True
        if candidate_name and expected_name and candidate_name == expected_name:
            return True
        return False

    async def query_data(self, query: str, mode: str = "hybrid", top_k: int = 10) -> Dict[str, Any]:
        payload = await self.lightrag_client.query_data(query, mode=mode, top_k=top_k)
        data = payload.get("data") or {}
        return {
            "raw": payload,
            "entities": list(data.get("entities") or []),
            "relationships": list(data.get("relationships") or []),
            "chunks": list(data.get("chunks") or []),
            "references": list(data.get("references") or []),
            "metadata": payload.get("metadata") or {},
        }

    async def get_document_semantic_snapshot(
        self,
        doc_info: Dict[str, Any],
        *,
        query: str | None = None,
        top_k: int = 12,
    ) -> Dict[str, Any]:
        """Fetch the best-effort semantic material for one document via LightRAG query/data."""
        seed_query = (
            str(query or "").strip()
            or str(doc_info.get("filename") or "").strip()
            or str(doc_info.get("classification_result") or "").strip()
            or "文档主题"
        )

        payload = await self.query_data(seed_query, mode="hybrid", top_k=top_k)

        matched_chunks = [item for item in payload["chunks"] if self._matches_document(item, doc_info)]
        matched_relationships = [item for item in payload["relationships"] if self._matches_document(item, doc_info)]
        matched_entities = [item for item in payload["entities"] if self._matches_document(item, doc_info)]
        matched_references = [item for item in payload["references"] if self._matches_document(item, doc_info)]

        summary_parts: List[str] = []
        for chunk in matched_chunks[:4]:
            content = str(chunk.get("content") or "").strip()
            if content:
                summary_parts.append(content[:500])
        for entity in matched_entities[:8]:
            name = str(entity.get("entity_name") or "").strip()
            description = str(entity.get("description") or "").strip()
            if name and description:
                summary_parts.append(f"{name}: {description}")
            elif name:
                summary_parts.append(name)
        for relation in matched_relationships[:6]:
            src = str(relation.get("src_id") or "").strip()
            tgt = str(relation.get("tgt_id") or "").strip()
            description = str(relation.get("description") or "").strip()
            if src and tgt and description:
                summary_parts.append(f"{src} -> {tgt}: {description}")

        return {
            "query": seed_query,
            "summary_text": "\n".join(summary_parts).strip(),
            "chunks": matched_chunks,
            "relationships": matched_relationships,
            "entities": matched_entities,
            "references": matched_references,
            "metadata": payload.get("metadata") or {},
            "raw": payload.get("raw") or {},
        }

    async def list_graph_labels(self) -> List[str]:
        payload = await self.lightrag_client.list_graph_labels()
        if isinstance(payload, dict):
            items = payload.get("data") or payload.get("labels") or payload.get("items") or []
        else:
            items = payload
        return [str(item).strip() for item in items if str(item).strip()]

    async def get_graph(self, label: str, max_depth: int = 3, max_nodes: int = 1000) -> Dict[str, Any]:
        payload = await self.lightrag_client.get_graph(label, max_depth=max_depth, max_nodes=max_nodes)
        raw_nodes = list(payload.get("nodes") or payload.get("data", {}).get("nodes") or [])
        raw_edges = list(payload.get("edges") or payload.get("data", {}).get("edges") or [])

        degree_counter = defaultdict(int)
        edges = []
        for edge in raw_edges:
            source = edge.get("source") or edge.get("from") or edge.get("src")
            target = edge.get("target") or edge.get("to") or edge.get("tgt")
            label_text = edge.get("label") or edge.get("predicate") or edge.get("relation") or ""
            if not source or not target:
                continue
            degree_counter[str(source)] += 1
            degree_counter[str(target)] += 1
            edges.append(
                {
                    "id": edge.get("id") or f"{source}:{label_text}:{target}",
                    "from": str(source),
                    "to": str(target),
                    "label": str(label_text),
                    "doc_id": edge.get("doc_id") or edge.get("file_path") or edge.get("reference_id"),
                }
            )

        nodes = []
        for node in raw_nodes:
            node_id = node.get("id") or node.get("node_id") or node.get("name") or node.get("label")
            if not node_id:
                continue
            nodes.append(
                {
                    "id": str(node_id),
                    "label": str(node.get("label") or node.get("name") or node_id),
                    "title": str(node.get("title") or node.get("description") or node.get("label") or node_id),
                    "degree": int(node.get("degree") or degree_counter[str(node_id)] or 0),
                    "type": node.get("type") or node.get("category") or "entity",
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_docs": len({str(edge.get("doc_id") or "") for edge in edges if str(edge.get("doc_id") or "").strip()}),
            },
            "label": label,
            "raw": payload,
        }
