import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.topics as topics_api  # noqa: E402


class _FakeSemanticService:
    async def list_graph_labels(self):
        return ["财务管理"]

    async def get_graph(self, label: str, max_depth: int = 3, max_nodes: int = 1000):
        assert label == "财务管理"
        assert max_depth == 3
        assert max_nodes == 1000
        return {
            "label": label,
            "nodes": [
                {"id": "预算审批", "label": "预算审批", "degree": 1},
                {"id": "财务制度", "label": "财务制度", "degree": 1},
            ],
            "edges": [
                {"from": "预算审批", "to": "财务制度", "label": "属于", "doc_id": "/tmp/预算制度.docx"}
            ],
            "stats": {"total_nodes": 2, "total_edges": 1, "total_docs": 1},
        }


def test_get_graph_labels_uses_lightrag_semantic_service(monkeypatch):
    monkeypatch.setattr(topics_api, "semantic_service", _FakeSemanticService())

    payload = asyncio.run(topics_api.get_graph_labels())

    assert payload["code"] == 200
    assert payload["data"]["items"] == ["财务管理"]
    assert payload["data"]["total"] == 1


def test_get_knowledge_graph_uses_lightrag_graph(monkeypatch):
    monkeypatch.setattr(topics_api, "semantic_service", _FakeSemanticService())

    payload = asyncio.run(topics_api.get_knowledge_graph(label=None, doc_ids=None, max_depth=3, max_nodes=1000))

    assert payload["code"] == 200
    assert payload["data"]["label"] == "财务管理"
    assert payload["data"]["stats"]["total_nodes"] == 2
    assert payload["data"]["edges"][0]["label"] == "属于"


def test_related_documents_uses_lightrag_graph_edges(monkeypatch):
    monkeypatch.setattr(topics_api, "semantic_service", _FakeSemanticService())

    payload = asyncio.run(topics_api.get_related_documents("预算审批"))

    assert payload["code"] == 200
    assert payload["data"]["center_entity"] == "预算审批"
    assert payload["data"]["direct_relations"][0]["predicate"] == "属于"
    assert "财务制度" in payload["data"]["related_entities"]
