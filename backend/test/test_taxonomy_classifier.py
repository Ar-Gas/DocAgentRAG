import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_public_taxonomy_classifier_uses_v3_hierarchical_classifier(monkeypatch):
    class FakeV3:
        async def classify(self, document_id, content, filename="", file_type=""):
            return {
                "classification_id": "books.computer.programming_language",
                "classification_leaf_id": "books.computer.programming_language",
                "classification_label": "编程语言书籍",
                "classification_path": ["图书资料", "计算机图书", "编程语言书籍"],
                "classification_domain": "图书资料",
                "classification_score": 0.91,
                "classification_confidence": 0.91,
                "classification_source": "llm_hierarchical",
                "classification_candidates": ["books.computer.programming_language"],
                "classification_review_status": "accepted",
                "classification_issue_code": None,
                "taxonomy_version": "taxonomy_v3",
            }

    import app.services.taxonomy_classifier as taxonomy_classifier_module

    monkeypatch.setattr(
        taxonomy_classifier_module,
        "TaxonomyV3Classifier",
        lambda llm_gateway=None: FakeV3(),
    )

    result = asyncio.run(
        taxonomy_classifier_module.TaxonomyClassifier().classify(
            "doc-1",
            "Rust 所有权和借用",
            filename="Rust编程.pdf",
            file_type=".pdf",
        )
    )

    assert result["taxonomy_version"] == "taxonomy_v3"
    assert result["classification_path"] == ["图书资料", "计算机图书", "编程语言书籍"]
    assert result["classification_issue_code"] is None
