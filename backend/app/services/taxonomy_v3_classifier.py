from __future__ import annotations

from typing import Any

from app.core.logger import logger
from app.domain.llm.gateway import LLMGateway
from app.domain.taxonomy.universal_taxonomy_v3 import (
    KEYWORD_OVERRIDES,
    TAXONOMY_VERSION,
    format_path,
    get_all_labels,
    get_domain_fallback,
    get_domain_options,
    get_labels_by_domain,
    infer_domain_from_filename,
)
from app.services.taxonomy_v3_llm_protocol import (
    ParsedClassification,
    parse_classification_output,
)


class TaxonomyV3Classifier:
    def __init__(self, llm_gateway: LLMGateway | None = None):
        self.llm_gateway = llm_gateway or LLMGateway()

    async def classify(
        self,
        document_id: str,
        content: str,
        filename: str = "",
        file_type: str = "",
    ) -> dict[str, Any]:
        del document_id

        sample = self._build_content_sample(content)
        domain = await self._select_domain(filename, file_type, sample)
        heuristic_label = self._select_keyword_label(domain, filename, sample)
        selected = await self._select_leaf(domain, filename, file_type, sample)
        if selected is None:
            if heuristic_label:
                return self._build_result(
                    heuristic_label,
                    score=0.72,
                    source="llm_hierarchical_fallback",
                    is_fallback=True,
                    reason="LLM 输出无法匹配合法三级目录，按文件名和正文关键词选择具体叶子类。",
                )
            return self._build_fallback_result(domain)

        label = self._find_domain_label(domain, selected.label_id)
        if not label:
            if heuristic_label:
                return self._build_result(
                    heuristic_label,
                    score=0.72,
                    source="llm_hierarchical_fallback",
                    is_fallback=True,
                    reason="LLM 输出的叶子类不合法，按文件名和正文关键词选择具体叶子类。",
                )
            return self._build_fallback_result(domain)

        if heuristic_label and heuristic_label.get("id") != label.get("id"):
            heuristic_score = self._score_keyword_label(
                heuristic_label,
                str(filename or "").lower(),
                str(sample or "").lower(),
            )
            selected_score = self._score_keyword_label(
                label,
                str(filename or "").lower(),
                str(sample or "").lower(),
            )
            if heuristic_score >= 4 and heuristic_score > selected_score:
                label = heuristic_label
                selected = ParsedClassification(
                    path=list(label.get("path") or []),
                    label_id=str(label.get("id") or ""),
                    is_fallback=True,
                    confidence=max(selected.confidence, 0.72),
                    reason="文件名强关键词命中更具体叶子类，覆盖 LLM 的泛化选择。",
                )

        if (selected.is_fallback or label.get("fallback")) and heuristic_label:
            label = heuristic_label
            selected = ParsedClassification(
                path=list(label.get("path") or []),
                label_id=str(label.get("id") or ""),
                is_fallback=True,
                confidence=max(selected.confidence, 0.72),
                reason=selected.reason or "兜底输出被关键词具体类替换。",
            )

        is_fallback = selected.is_fallback or bool(label.get("fallback"))
        source = "llm_hierarchical_fallback" if is_fallback else "llm_hierarchical"
        return self._build_result(
            label,
            score=selected.confidence or 0.65,
            source=source,
            is_fallback=is_fallback,
            reason=selected.reason,
        )

    async def _select_domain(self, filename: str, file_type: str, sample: str) -> str:
        prompt = self._build_domain_prompt(filename, file_type, sample)
        parsed = await self._call_and_parse(prompt)
        if parsed and parsed.path[0] in get_domain_options():
            return parsed.path[0]

        retry_prompt = prompt + "\n\n只能从候选一级域中选择一个，并按固定格式返回。"
        parsed = await self._call_and_parse(retry_prompt)
        if parsed and parsed.path[0] in get_domain_options():
            return parsed.path[0]

        return infer_domain_from_filename(filename, file_type)

    async def _select_leaf(
        self,
        domain: str,
        filename: str,
        file_type: str,
        sample: str,
    ) -> ParsedClassification | None:
        prompt = self._build_leaf_prompt(domain, filename, file_type, sample)
        parsed = await self._call_and_parse(prompt)
        if parsed and parsed.path[0] == domain:
            return parsed

        retry_prompt = prompt + "\n\n返回路径必须完全来自候选三级目录，不得新造分类。"
        parsed = await self._call_and_parse(retry_prompt)
        if parsed and parsed.path[0] == domain:
            return parsed
        return None

    async def _call_and_parse(self, prompt: str) -> ParsedClassification | None:
        try:
            response = await self.llm_gateway.call(
                prompt,
                task="classify",
                max_tokens=160,
                temperature=0.0,
                use_cache=False,
            )
        except Exception as exc:
            logger.warning("taxonomy_v3_llm_call_failed: {}", exc)
            return None
        return parse_classification_output(response.content)

    def _build_domain_prompt(self, filename: str, file_type: str, sample: str) -> str:
        domains = "\n".join(f"- {domain}" for domain in get_domain_options())
        return (
            "你是文档分类助手。请先选择最合适的一级域。\n"
            "候选一级域：\n"
            f"{domains}\n\n"
            f"文件名: {filename}\n"
            f"扩展名: {file_type}\n"
            f"正文样本: {sample}\n\n"
            "按固定格式返回：\n"
            "一级域: <候选一级域之一>\n"
            "二级类: <该一级域的兜底二级类>\n"
            "三级类: <该一级域的兜底三级类>\n"
            "是否兜底: 是\n"
            "置信度: 0.0到1.0\n"
            "依据: <一句话依据>"
        )

    def _build_leaf_prompt(self, domain: str, filename: str, file_type: str, sample: str) -> str:
        options = "\n".join(format_path(label) for label in get_labels_by_domain(domain))
        return (
            "你是文档分类助手。请从候选三级目录中选择一个最合适的真实路径。\n"
            f"已确定一级域: {domain}\n"
            "候选三级目录：\n"
            f"{options}\n\n"
            f"文件名: {filename}\n"
            f"扩展名: {file_type}\n"
            f"正文样本: {sample}\n\n"
            "按固定格式返回：\n"
            "一级域: <一级域>\n"
            "二级类: <候选路径中的二级类>\n"
            "三级类: <候选路径中的三级类>\n"
            "是否兜底: 是或否\n"
            "置信度: 0.0到1.0\n"
            "依据: <一句话依据>"
        )

    def _build_fallback_result(self, domain: str) -> dict[str, Any]:
        fallback = get_domain_fallback(domain) or get_domain_fallback(
            infer_domain_from_filename("", "")
        )
        return self._build_result(
            fallback,
            score=0.35,
            source="llm_hierarchical_fallback",
            is_fallback=True,
            reason="LLM 输出无法匹配合法三级目录，使用域内兜底叶子类。",
        )

    @staticmethod
    def _find_domain_label(domain: str, label_id: str) -> dict[str, Any] | None:
        for label in get_labels_by_domain(domain):
            if label.get("id") == label_id:
                return label
        return None

    @staticmethod
    def _select_keyword_label(domain: str, filename: str, sample: str) -> dict[str, Any] | None:
        filename_text = str(filename or "").lower()
        sample_text = str(sample or "").lower()
        matches: list[tuple[int, int, dict[str, Any]]] = []
        for index, label in enumerate(get_labels_by_domain(domain)):
            if label.get("fallback"):
                continue
            score = TaxonomyV3Classifier._score_keyword_label(label, filename_text, sample_text)
            if score:
                matches.append((score, index, label))

        if not matches and domain != "图书资料":
            for index, label in enumerate(get_all_labels()):
                if label.get("fallback"):
                    continue
                score = TaxonomyV3Classifier._score_keyword_label(label, filename_text, sample_text)
                if score:
                    matches.append((score, index, label))

        if not matches:
            return None
        matches.sort(key=lambda item: (-item[0], item[1], str(item[2].get("id") or "")))
        return matches[0][2]

    @staticmethod
    def _score_keyword_label(label: dict[str, Any], filename_text: str, sample_text: str) -> int:
        path = tuple(label.get("path") or [])
        keywords = KEYWORD_OVERRIDES.get(path)
        if not keywords:
            keywords = [label.get("label", ""), *list(label.get("aliases") or [])]

        score = 0
        for keyword in keywords:
            normalized_keyword = str(keyword or "").strip().lower()
            if not normalized_keyword:
                continue
            if normalized_keyword in filename_text:
                score += 4
            if normalized_keyword in sample_text:
                score += 1
        return score

    @staticmethod
    def _build_content_sample(content: str) -> str:
        text = str(content or "").strip()
        if len(text) <= 2400:
            return text
        head = text[:2400]
        middle_start = max(0, len(text) // 2 - 400)
        middle = text[middle_start : middle_start + 800]
        tail = text[-800:]
        return "\n".join([head, middle, tail])

    @staticmethod
    def _build_result(
        label: dict[str, Any],
        *,
        score: float,
        source: str,
        is_fallback: bool,
        reason: str,
    ) -> dict[str, Any]:
        path = list(label.get("path") or [])
        confidence = round(max(0.0, min(float(score), 1.0)), 4)
        source_value = source
        if is_fallback and source_value == "llm_hierarchical":
            source_value = "llm_hierarchical_fallback"
        return {
            "classification_id": label.get("id", ""),
            "classification_leaf_id": label.get("id", ""),
            "classification_label": label.get("label", ""),
            "classification_path": path,
            "classification_domain": path[0] if path else None,
            "classification_score": confidence,
            "classification_confidence": confidence,
            "classification_source": source_value,
            "classification_candidates": [label.get("id", "")],
            "classification_review_status": "accepted",
            "classification_issue_code": None,
            "classification_is_fallback": bool(is_fallback),
            "classification_reason": str(reason or "")[:300],
            "taxonomy_version": TAXONOMY_VERSION,
        }
