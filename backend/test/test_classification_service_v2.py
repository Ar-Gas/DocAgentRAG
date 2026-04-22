import app.services.classification_service as classification_service_module
from app.services.classification_service import ClassificationService


def test_classification_service_persists_v2_assignment_fields(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {"id": document_id, "filename": "guide.pdf", "file_type": ".pdf"},
    )
    monkeypatch.setattr(
        classification_service_module,
        "get_document_content_record",
        lambda document_id: {"full_content": "值班流程、故障处理、巡检和变更窗口"},
    )
    monkeypatch.setattr(classification_service_module, "is_error_document", lambda *args, **kwargs: False)

    updates = []
    monkeypatch.setattr(
        classification_service_module,
        "update_document_info",
        lambda document_id, updated_info: updates.append(updated_info) or True,
    )

    class FakeTaxonomyClassifier:
        async def classify(self, document_id, content, filename="", file_type=""):
            return {
                "classification_id": "tech.operations_manual",
                "classification_leaf_id": "tech.operations_manual",
                "classification_label": "运维手册",
                "classification_path": ["技术文档", "运维体系", "运维手册"],
                "classification_domain": "技术文档",
                "classification_score": 0.88,
                "classification_confidence": 0.88,
                "classification_source": "llm",
                "classification_candidates": ["tech.operations_manual"],
                "classification_review_status": "accepted",
                "classification_issue_code": None,
                "taxonomy_version": "taxonomy_v2",
            }

    monkeypatch.setattr(classification_service_module, "TaxonomyClassifier", FakeTaxonomyClassifier)

    result = ClassificationService().classify("doc-1")

    assert result["topic_id"] == "tech.operations_manual"
    assert result["topic_path"] == ["技术文档", "运维体系", "运维手册"]
    assert updates[0]["taxonomy_version"] == "taxonomy_v2"
    assert updates[0]["classification_leaf_id"] == "tech.operations_manual"
    assert updates[0]["classification_domain"] == "技术文档"
    assert updates[0]["classification_confidence"] == 0.88
