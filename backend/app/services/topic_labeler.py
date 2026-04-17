import json
import re
from typing import Any, Dict, List

from app.core.logger import logger
from app.domain.classification_contract import (
    GENERIC_LABELS,
    SPECIAL_ERROR_LABEL,
    first_usable_text,
    is_unusable_classification_text,
    normalize_classification_label,
)
from utils.smart_retrieval import _call_llm, is_llm_available

_GENERIC_LABELS = GENERIC_LABELS


class TopicLabeler:
    def __init__(self):
        self._disable_remote_labeling = False

    def label_parent_topic(self, representatives: List[Dict[str, Any]]) -> Dict[str, str]:
        prompt = self._build_parent_prompt(representatives)
        return self._label_with_prompt(prompt, representatives=representatives)

    def label_child_topic(self, parent_label: str, representatives: List[Dict[str, Any]]) -> Dict[str, str]:
        prompt = self._build_child_prompt(parent_label, representatives)
        return self._label_with_prompt(prompt, representatives=representatives, parent_label=parent_label)

    def _label_with_prompt(
        self,
        prompt: str,
        *,
        representatives: List[Dict[str, Any]],
        parent_label: str | None = None,
    ) -> Dict[str, str]:
        if self._representatives_are_unusable(representatives):
            return self._error_label_payload()

        if self._disable_remote_labeling or not is_llm_available():
            return self._fallback_label(representatives, parent_label=parent_label)

        try:
            content = _call_llm(prompt, max_tokens=200, temperature=0.2)
            if not content:
                self._disable_remote_labeling = True
                raise RuntimeError("LLM returned empty topic label")

            parsed = self._parse_json_payload(content)
            label = self._validate_label((parsed.get("label") or "").strip(), parent_label=parent_label)
            summary = (parsed.get("summary") or "").strip()
            if not summary:
                summary = (
                    "文档内容异常或提取结果不可用，已归类为 Error。"
                    if label == SPECIAL_ERROR_LABEL
                    else f"围绕{label}相关内容的主题聚类结果"
                )
            return {"label": label, "summary": summary}
        except Exception as exc:
            logger.warning("Topic labeler fallback to local heuristic: {}", exc)
            return self._fallback_label(representatives, parent_label=parent_label)

    def _fallback_label(self, representatives: List[Dict[str, Any]], parent_label: str | None = None) -> Dict[str, str]:
        if self._representatives_are_unusable(representatives):
            return self._error_label_payload()

        label = (
            self._extract_shared_label(representatives, parent_label=parent_label)
            or self._extract_primary_phrase(representatives, parent_label=parent_label)
            or SPECIAL_ERROR_LABEL
        )
        label = self._validate_label(label[:8], parent_label=parent_label, allow_generic_fallback=True)
        return {
            "label": label,
            "summary": (
                "文档内容异常或提取结果不可用，已归类为 Error。"
                if label == SPECIAL_ERROR_LABEL
                else f"基于代表文档内容提取的本地主题标签：{label}"
            ),
        }

    def _extract_shared_label(
        self,
        representatives: List[Dict[str, Any]],
        *,
        parent_label: str | None = None,
    ) -> str:
        candidate_sets = []
        for item in representatives[:5]:
            texts = self._representative_texts(item)
            candidates = set()
            for text in texts:
                if is_unusable_classification_text(text):
                    continue
                for sequence in re.findall(r"[\u4e00-\u9fff]{2,20}", text):
                    candidates.update(self._expand_ngrams(sequence))
            if candidates:
                candidate_sets.append(candidates)

        if len(candidate_sets) < 2:
            return ""

        shared = set.intersection(*candidate_sets)
        filtered = [
            item
            for item in shared
            if self._is_valid_candidate(item, parent_label=parent_label)
        ]
        if not filtered:
            return ""

        return sorted(filtered, key=lambda item: (-len(item), item))[0]

    def _extract_primary_phrase(
        self,
        representatives: List[Dict[str, Any]],
        *,
        parent_label: str | None = None,
    ) -> str:
        for item in representatives[:5]:
            for text in self._representative_texts(item):
                if is_unusable_classification_text(text):
                    continue
                for piece in re.split(r"[，。；：、,\n/]|与|及|和|的", text):
                    candidate = piece.strip()
                    if len(candidate) > 8:
                        candidate = candidate[:8]
                    if self._is_valid_candidate(candidate, parent_label=parent_label):
                        return candidate
        return ""

    @staticmethod
    def _representative_texts(item: Dict[str, Any]) -> List[str]:
        return [
            (item.get("excerpt") or "").strip(),
            (item.get("summary_source") or "").strip(),
            (item.get("filename") or "").strip(),
        ]

    @staticmethod
    def _expand_ngrams(sequence: str) -> List[str]:
        candidates = []
        max_len = min(8, len(sequence))
        for size in range(max_len, 1, -1):
            for start in range(0, len(sequence) - size + 1):
                candidates.append(sequence[start : start + size])
        return candidates

    def _validate_label(
        self,
        label: str,
        *,
        parent_label: str | None = None,
        allow_generic_fallback: bool = False,
    ) -> str:
        normalized = normalize_classification_label(label, parent_label=parent_label)
        if normalized is None:
            raise RuntimeError("topic label is empty")
        if normalized == SPECIAL_ERROR_LABEL:
            return SPECIAL_ERROR_LABEL
        if len(normalized) > 8:
            raise RuntimeError(f"topic label too long: {normalized}")
        if normalized in _GENERIC_LABELS and not allow_generic_fallback:
            raise RuntimeError(f"topic label too generic: {label}")
        if parent_label and normalized == parent_label:
            raise RuntimeError("Child topic label duplicated parent label")
        return normalized

    def _is_valid_candidate(self, candidate: str, *, parent_label: str | None = None) -> bool:
        normalized = normalize_classification_label(candidate, parent_label=parent_label)
        return bool(normalized and normalized != SPECIAL_ERROR_LABEL)

    @staticmethod
    def _build_parent_prompt(representatives: List[Dict[str, Any]]) -> str:
        docs = TopicLabeler._format_representatives(representatives)
        return (
            "你现在是一个资深的跨国企业档案管理员。\n"
            "请根据以下几篇代表文档的内容摘要，为它们归纳一个共同的一级语义分类标签。\n"
            "要求：\n"
            "1. 标签必须是具体的业务领域或文档类型，如：财务制度、采购管理、劳动合同、会议记录。\n"
            "2. 绝对不能使用无意义的词汇，如：文档、正文、一个、测试、相关内容。\n"
            "3. 如果摘要主要是解析失败、OCR失败、网页拦截页或无效文本，请输出 Error。\n"
            "4. 除 Error 外，标签字数控制在 4-8 个字以内。\n"
            "5. 只返回 JSON，格式为 {\"label\":\"...\",\"summary\":\"...\"}。\n"
            f"代表文档：\n{docs}"
        )

    @staticmethod
    def _build_child_prompt(parent_label: str, representatives: List[Dict[str, Any]]) -> str:
        docs = TopicLabeler._format_representatives(representatives)
        return (
            "你现在是一个资深的跨国企业档案管理员。\n"
            f"父级业务主题是：{parent_label}\n"
            "请根据以下几篇代表文档的内容摘要，为它们归纳一个共同的二级语义分类标签。\n"
            "要求：\n"
            "1. 标签必须是具体的业务领域或文档类型，如：劳动合同、财务月报、前端开发规范、会议记录。\n"
            "2. 绝对不能使用无意义的词汇，如：文档、正文、一个、测试、相关内容。\n"
            "3. 不要直接复用父级标签原词；如果摘要主要是解析失败、OCR失败、网页拦截页或无效文本，请输出 Error。\n"
            "4. 除 Error 外，标签字数控制在 4-8 个字以内。\n"
            "5. 只返回 JSON，格式为 {\"label\":\"...\",\"summary\":\"...\"}。\n"
            f"代表文档：\n{docs}"
        )

    @staticmethod
    def _format_representatives(representatives: List[Dict[str, Any]]) -> str:
        lines = []
        for index, item in enumerate(representatives[:5], start=1):
            excerpt = first_usable_text(
                [
                    item.get("excerpt") or "",
                    item.get("summary_source") or "",
                    item.get("filename") or "",
                ]
            )
            excerpt = re.sub(r"\s+", " ", excerpt)[:180]
            lines.append(f"{index}. 文件名：{item.get('filename', '')}\n摘要：{excerpt}")
        return "\n".join(lines)

    @staticmethod
    def _representatives_are_unusable(representatives: List[Dict[str, Any]]) -> bool:
        meaningful_texts = 0
        for item in representatives[:5]:
            excerpt = first_usable_text(
                [
                    item.get("excerpt") or "",
                    item.get("summary_source") or "",
                ]
            )
            if excerpt:
                meaningful_texts += 1
        return meaningful_texts == 0

    @staticmethod
    def _error_label_payload() -> Dict[str, str]:
        return {
            "label": SPECIAL_ERROR_LABEL,
            "summary": "文档内容异常或提取结果不可用，已归类为 Error。",
        }

    @staticmethod
    def _parse_json_payload(content: str) -> Dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise RuntimeError(f"LLM topic label JSON parse failed: {content}")

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise RuntimeError(f"LLM topic label payload invalid: {content}")
        return parsed
