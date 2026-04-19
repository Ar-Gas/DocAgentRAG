"""固定 taxonomy 分类器。"""

from __future__ import annotations

import os
from typing import Any

from app.core.logger import logger
from app.domain.llm.gateway import LLMGateway
from app.domain.taxonomy.internet_enterprise_taxonomy import (
    get_all_labels,
    get_label_by_id,
    search_by_keyword,
)


class TaxonomyClassifier:
    """
    固定 taxonomy 分类器，替代 TopicTreeService 作为 classification_result 的唯一来源。
    分三步：模板候选召回 → 受约束 LLM 选择 → 固定模板兜底
    """

    _WEAK_RECALL_THRESHOLD = 0.5
    _FORCED_CONFIDENCE_FLOOR = 0.2
    _FORCED_CONFIDENCE_CAP = 0.49
    _DEFAULT_TEMPLATE_LABEL_ID = "admin.notice"

    def __init__(self, llm_gateway: LLMGateway | None = None):
        self.llm_gateway = llm_gateway or LLMGateway()

    async def classify(
        self,
        document_id: str,
        content: str,
        filename: str = "",
        file_type: str = "",
    ) -> dict:
        """
        Returns:
        {
            "classification_id": str,
            "classification_label": str,
            "classification_path": list,
            "classification_score": float,
            "classification_source": str,
            "classification_candidates": list[str],
        }
        """
        del document_id

        normalized_content = str(content or "")[:2000]
        normalized_filename = str(filename or "")
        normalized_file_type = self._normalize_file_type(
            file_type or os.path.splitext(normalized_filename)[1]
        )

        all_labels = get_all_labels()
        recalled = self._recall_candidates(
            normalized_content,
            normalized_filename,
            normalized_file_type,
            top_k=len(all_labels),
        )
        template_candidates = self._build_template_candidates(recalled, all_labels)
        candidate_ids = [label["id"] for label, _score in template_candidates[:5]]
        has_strong_enough_recall = (
            bool(recalled) and recalled[0][1] >= self._WEAK_RECALL_THRESHOLD
        )

        if self._should_use_keyword_result(recalled):
            keyword_label, keyword_score = recalled[0]
            return self._build_result(
                keyword_label,
                score=self._score_to_confidence(keyword_score),
                source="keyword",
                candidate_ids=candidate_ids,
            )

        if not template_candidates:
            return self._build_result(
                self._fallback_label(),
                score=0.0,
                source="fallback",
                candidate_ids=candidate_ids,
            )

        selected_label_id, llm_confidence = await self._llm_select(
            normalized_content,
            [label for label, _score in template_candidates],
        )
        if not selected_label_id:
            return self._build_forced_keyword_result(template_candidates, candidate_ids)

        selected_label = get_label_by_id(selected_label_id)
        if not selected_label:
            return self._build_forced_keyword_result(template_candidates, candidate_ids)

        keyword_score = next(
            (
                score
                for label, score in template_candidates
                if label.get("id") == selected_label_id
            ),
            0.0,
        )
        final_score = max(llm_confidence, self._score_to_confidence(keyword_score))
        if not has_strong_enough_recall or final_score < self._WEAK_RECALL_THRESHOLD:
            return self._build_result(
                selected_label,
                score=self._forced_confidence(final_score),
                source="llm_forced",
                candidate_ids=candidate_ids,
            )

        return self._build_result(
            selected_label,
            score=final_score,
            source="llm",
            candidate_ids=candidate_ids,
        )

    def _recall_candidates(
        self,
        content: str,
        filename: str,
        file_type: str,
        top_k: int = 8,
    ) -> list[tuple[dict, float]]:
        """
        候选召回：
        1. 调用 internet_enterprise_taxonomy.search_by_keyword(content, filename_text=filename)
        2. 如果 file_type 匹配某标签 file_types，额外加分 +0.3
        3. 返回 top_k 结果
        """
        if top_k <= 0:
            return []

        all_labels = get_all_labels()
        score_map = {
            label["id"]: float(score)
            for label, score in search_by_keyword(
                content,
                top_k=len(all_labels),
                filename_text=filename,
            )
        }

        normalized_file_type = self._normalize_file_type(file_type)
        if normalized_file_type:
            for label in all_labels:
                label_file_types = {
                    self._normalize_file_type(item)
                    for item in label.get("file_types", [])
                }
                if normalized_file_type in label_file_types:
                    score_map[label["id"]] = score_map.get(label["id"], 0.0) + 0.3

        recalled = [
            (label, score_map[label["id"]])
            for label in all_labels
            if label["id"] in score_map
        ]
        recalled.sort(key=lambda item: (-item[1], item[0].get("id", "")))
        return recalled[:top_k]

    def _build_template_candidates(
        self,
        recalled: list[tuple[dict, float]],
        all_labels: list[dict],
    ) -> list[tuple[dict, float]]:
        score_map = {
            str(label.get("id") or ""): float(score)
            for label, score in recalled
            if label.get("id")
        }
        order_map = {
            str(label.get("id") or ""): index
            for index, label in enumerate(all_labels)
            if label.get("id")
        }
        candidates = [
            (label, score_map.get(str(label.get("id") or ""), 0.0))
            for label in all_labels
            if label.get("id")
        ]

        candidates.sort(key=lambda item: self._template_candidate_sort_key(item, order_map))
        return candidates

    def _template_candidate_sort_key(
        self,
        item: tuple[dict, float],
        order_map: dict[str, int],
    ) -> tuple[float, int, int]:
        label, score = item
        label_id = str(label.get("id") or "")
        default_rank = 0 if score <= 0 and label_id == self._DEFAULT_TEMPLATE_LABEL_ID else 1
        return (-float(score), default_rank, order_map.get(label_id, 9999))

    def _build_forced_keyword_result(
        self,
        template_candidates: list[tuple[dict, float]],
        candidate_ids: list[str],
    ) -> dict:
        if not template_candidates:
            return self._build_result(
                self._fallback_label(),
                score=0.0,
                source="fallback",
                candidate_ids=candidate_ids,
            )

        selected_label, keyword_score = template_candidates[0]
        return self._build_result(
            selected_label,
            score=self._forced_confidence(self._score_to_confidence(keyword_score)),
            source="keyword_forced",
            candidate_ids=candidate_ids,
        )

    async def _llm_select(
        self,
        content: str,
        candidates: list[dict],
    ) -> tuple[str | None, float]:
        """
        调用 LLMGateway，传入候选标签列表，让模型只从候选中选一个。
        Prompt 格式（中文）：
            你是一个企业办公文档分类助手。
            请根据以下文档内容，从候选分类标签中选出最合适的一个。
            只能返回候选列表中的标签名称，不得新造标签，不得返回其他内容。

            候选标签：{labels}
            文档内容（前2000字）：{content}

            直接返回标签名称：
        Returns: (selected_label_id_or_None, confidence_score)
        """
        if not candidates:
            return None, 0.0

        labels_text = "\n".join(
            f"- {item['id']} | {' > '.join(item.get('path') or [])} | {item['label']}"
            for item in candidates
        )
        prompt = (
            "你是一个企业办公文档分类助手。\n"
            "请根据以下文档内容，从候选分类标签中选出最合适的一个。\n"
            "只能返回候选列表中的分类ID或标签名称，不得新造标签，不得返回其他内容。\n\n"
            f"候选标签：\n{labels_text}\n"
            f"文档内容（前2000字）：{str(content or '')[:2000]}\n\n"
            "直接返回分类ID或标签名称："
        )

        try:
            response = await self.llm_gateway.call(
                prompt,
                task="classify",
                max_tokens=50,
                temperature=0.0,
                use_cache=False,
            )
        except Exception as exc:
            logger.warning("taxonomy llm select failed: %s", exc)
            return None, 0.0

        selected_name = self._normalize_model_output(response.content)
        if not selected_name:
            return None, 0.0

        selected_label = None
        exact_match = True
        for item in candidates:
            if item.get("id") == selected_name or item.get("label") == selected_name:
                selected_label = item
                break

        if selected_label is None:
            exact_match = False
            for item in candidates:
                label = str(item.get("label") or "")
                label_id = str(item.get("id") or "")
                path = " > ".join(item.get("path") or [])
                if (
                    (label and (label in selected_name or selected_name in label))
                    or (label_id and label_id in selected_name)
                    or (path and (path in selected_name or selected_name in path))
                ):
                    selected_label = item
                    break

        if selected_label is None:
            return None, 0.0

        rank = next(
            index
            for index, item in enumerate(candidates)
            if item.get("id") == selected_label.get("id")
        )
        base_confidence = 0.82 - (rank * 0.08)
        if not exact_match:
            base_confidence -= 0.08

        return selected_label.get("id"), max(0.5, min(round(base_confidence, 4), 0.95))

    def _fallback_label(self) -> dict:
        """
        当候选分数全部低于 0.5 或 LLM 失败时，返回兜底标签。
        兜底标签 id: "admin.unclassified"，label: "待人工确认"，score: 0.0
        """
        return {
            "id": "admin.unclassified",
            "path": ["行政办公", "未分类", "待人工确认"],
            "label": "待人工确认",
            "aliases": [],
            "keywords": [],
            "negative_keywords": [],
            "file_types": [],
        }

    @staticmethod
    def _normalize_file_type(file_type: str) -> str:
        normalized = str(file_type or "").strip().lower()
        if not normalized:
            return ""
        if not normalized.startswith("."):
            normalized = f".{normalized}"
        return normalized

    @staticmethod
    def _normalize_model_output(raw_text: str) -> str:
        text = str(raw_text or "").strip()
        for prefix in ("标签：", "标签:", "分类：", "分类:", "分类标签：", "分类标签:"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        return text.strip().strip("\"'`")

    @staticmethod
    def _score_to_confidence(score: float) -> float:
        return max(0.0, min(round(float(score) / 4.0, 4), 1.0))

    def _forced_confidence(self, score: float) -> float:
        if score <= 0:
            return self._FORCED_CONFIDENCE_FLOOR
        return min(
            self._FORCED_CONFIDENCE_CAP,
            max(self._FORCED_CONFIDENCE_FLOOR, round(float(score), 4)),
        )

    def _should_use_keyword_result(self, recalled: list[tuple[dict, float]]) -> bool:
        if not recalled:
            return False

        top_score = recalled[0][1]
        second_score = recalled[1][1] if len(recalled) > 1 else 0.0
        return top_score >= 4.2 and (top_score - second_score) >= 1.0

    @staticmethod
    def _build_result(
        label: dict[str, Any],
        *,
        score: float,
        source: str,
        candidate_ids: list[str],
    ) -> dict:
        return {
            "classification_id": label.get("id", ""),
            "classification_label": label.get("label", ""),
            "classification_path": list(label.get("path") or []),
            "classification_score": round(float(score), 4),
            "classification_source": source,
            "classification_candidates": candidate_ids[:5],
        }
