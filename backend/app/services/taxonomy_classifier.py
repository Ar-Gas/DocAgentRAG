"""Public taxonomy classifier facade."""

from __future__ import annotations

from app.domain.llm.gateway import LLMGateway
from app.services.taxonomy_v3_classifier import TaxonomyV3Classifier


class TaxonomyClassifier:
    def __init__(self, llm_gateway: LLMGateway | None = None):
        self._classifier = TaxonomyV3Classifier(llm_gateway=llm_gateway)

    async def classify(
        self,
        document_id: str,
        content: str,
        filename: str = "",
        file_type: str = "",
    ) -> dict:
        return await self._classifier.classify(
            document_id=document_id,
            content=content,
            filename=filename,
            file_type=file_type,
        )
