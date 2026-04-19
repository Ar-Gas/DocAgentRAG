import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.lightrag_semantic_service import LightRAGSemanticService  # noqa: E402


class _FakeLightRAGClient:
    async def query_data(self, query: str, mode: str = "hybrid", top_k: int = 10):
        return {
            "data": {
                "chunks": [
                    {"content": "预算审批流程包括提交和复核。", "file_path": "/tmp/预算制度.docx", "chunk_id": "c1"},
                    {"content": "无关文档内容", "file_path": "/tmp/other.docx", "chunk_id": "c2"},
                ],
                "entities": [
                    {"entity_name": "预算审批", "description": "财务流程", "file_path": "/tmp/预算制度.docx"},
                    {"entity_name": "无关实体", "description": "其他", "file_path": "/tmp/other.docx"},
                ],
                "relationships": [
                    {
                        "src_id": "预算",
                        "tgt_id": "审批",
                        "description": "预算需要审批",
                        "file_path": "/tmp/预算制度.docx",
                    }
                ],
                "references": [
                    {"reference_id": "1", "file_path": "/tmp/预算制度.docx"},
                    {"reference_id": "2", "file_path": "/tmp/other.docx"},
                ],
            },
            "metadata": {"query_mode": mode},
        }

    async def list_graph_labels(self):
        return {"labels": ["财务管理", "人力资源"]}

    async def get_graph(self, label: str, max_depth: int = 3, max_nodes: int = 1000):
        return {
            "nodes": [
                {"id": "预算审批", "label": "预算审批"},
                {"id": "财务制度", "label": "财务制度"},
            ],
            "edges": [
                {"source": "预算审批", "target": "财务制度", "label": "属于", "file_path": "/tmp/预算制度.docx"}
            ],
        }


def test_get_document_semantic_snapshot_filters_to_current_document():
    service = LightRAGSemanticService(lightrag_client=_FakeLightRAGClient())

    payload = asyncio.run(
        service.get_document_semantic_snapshot(
            {"filename": "预算制度.docx", "filepath": "/tmp/预算制度.docx"},
            top_k=5,
        )
    )

    assert len(payload["chunks"]) == 1
    assert len(payload["entities"]) == 1
    assert len(payload["relationships"]) == 1
    assert len(payload["references"]) == 1
    assert "预算审批流程包括提交和复核" in payload["summary_text"]
    assert "预算审批: 财务流程" in payload["summary_text"]


def test_get_graph_normalizes_nodes_edges_and_stats():
    service = LightRAGSemanticService(lightrag_client=_FakeLightRAGClient())

    payload = asyncio.run(service.get_graph("财务管理"))

    assert payload["label"] == "财务管理"
    assert payload["stats"]["total_nodes"] == 2
    assert payload["stats"]["total_edges"] == 1
    assert payload["stats"]["total_docs"] == 1
    assert payload["edges"][0]["from"] == "预算审批"
    assert payload["edges"][0]["to"] == "财务制度"
    assert payload["edges"][0]["label"] == "属于"
