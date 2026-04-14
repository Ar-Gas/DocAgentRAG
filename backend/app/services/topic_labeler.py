import json
import re
from typing import Any, Dict, List

from utils.smart_retrieval import _call_llm, is_llm_available

_GENERIC_LABELS = {
    "文档",
    "资料",
    "主题",
    "业务",
    "管理",
    "综合主题",
    "综合",
    "其他",
    "未分类",
}


class TopicLabeler:
    def label_parent_topic(self, representatives: List[Dict[str, Any]]) -> Dict[str, str]:
        prompt = self._build_parent_prompt(representatives)
        return self._label_with_prompt(prompt)

    def label_child_topic(self, parent_label: str, representatives: List[Dict[str, Any]]) -> Dict[str, str]:
        prompt = self._build_child_prompt(parent_label, representatives)
        return self._label_with_prompt(prompt, parent_label=parent_label)

    def _label_with_prompt(self, prompt: str, parent_label: str | None = None) -> Dict[str, str]:
        if not is_llm_available():
            raise RuntimeError("LLM unavailable for semantic topic tree generation")

        content = _call_llm(prompt, max_tokens=200, temperature=0.2)
        if not content:
            raise RuntimeError("LLM returned empty topic label")

        parsed = self._parse_json_payload(content)
        label = (parsed.get("label") or "").strip()
        summary = (parsed.get("summary") or "").strip()

        if not label:
            raise RuntimeError("LLM topic label is empty")
        if len(label) > 8:
            raise RuntimeError(f"LLM topic label too long: {label}")
        if label in _GENERIC_LABELS:
            raise RuntimeError(f"LLM topic label too generic: {label}")
        if parent_label and label == parent_label:
            raise RuntimeError("Child topic label duplicated parent label")

        return {"label": label, "summary": summary}

    @staticmethod
    def _build_parent_prompt(representatives: List[Dict[str, Any]]) -> str:
        docs = TopicLabeler._format_representatives(representatives)
        return (
            "你是企业知识库主题归纳助手。\n"
            "请根据以下几篇代表文档，提炼它们共同的一级业务主题。\n"
            "要求：\n"
            "1. 输出一个不超过8个字的中文短语。\n"
            "2. 必须是业务域，不是具体动作。\n"
            "3. 不要使用“文档、资料、主题、业务、管理、综合、其他”等通用词。\n"
            "4. 只返回 JSON，格式为 {\"label\":\"...\",\"summary\":\"...\"}。\n"
            f"代表文档：\n{docs}"
        )

    @staticmethod
    def _build_child_prompt(parent_label: str, representatives: List[Dict[str, Any]]) -> str:
        docs = TopicLabeler._format_representatives(representatives)
        return (
            "你是企业知识库主题归纳助手。\n"
            f"父级业务主题是：{parent_label}\n"
            "请根据以下几篇代表文档，提炼它们共同的二级具体业务主题。\n"
            "要求：\n"
            "1. 输出一个不超过8个字的中文短语。\n"
            "2. 必须是具体事项，不是泛化业务域。\n"
            "3. 不要复用父级主题原词，不要使用“文档、资料、主题、业务、管理、综合、其他”等通用词。\n"
            "4. 只返回 JSON，格式为 {\"label\":\"...\",\"summary\":\"...\"}。\n"
            f"代表文档：\n{docs}"
        )

    @staticmethod
    def _format_representatives(representatives: List[Dict[str, Any]]) -> str:
        lines = []
        for index, item in enumerate(representatives[:5], start=1):
            excerpt = (item.get("excerpt") or item.get("summary_source") or "").strip()
            excerpt = re.sub(r"\s+", " ", excerpt)[:180]
            lines.append(f"{index}. 文件名：{item.get('filename', '')}\n摘要：{excerpt}")
        return "\n".join(lines)

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
