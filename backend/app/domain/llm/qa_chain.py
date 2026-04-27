"""QA Chain - RAG 问答链"""
import json
import re
from typing import List, Dict, Any, Tuple
from app.domain.llm import prompts


class QAChain:
    """RAG 问答链"""

    @staticmethod
    def build_context(blocks: List[Dict[str, Any]]) -> str:
        """
        构造 RAG context

        Args:
            blocks: 检索到的文档块列表

        Returns:
            格式化的 context 字符串
        """
        context_parts = []
        for block in blocks[:10]:  # 最多用前 10 个块
            doc_id = block.get("doc_id", "")
            filename = block.get("filename", "")
            section = block.get("section", "")
            page_number = block.get("page_number")
            content = block.get("content", "")[:500]  # 限制长度

            # 格式：[文档ID | 文件名 §节号 P页码]: 内容
            doc_ref = f"[{doc_id}" if doc_id else "["
            if filename:
                doc_ref += f" | {filename}"
            if section:
                doc_ref += f" §{section}"
            if page_number:
                doc_ref += f" P{page_number}"
            doc_ref += "]: "

            context_parts.append(f"{doc_ref}{content}")

        return "\n\n".join(context_parts)

    @staticmethod
    def build_prompt(query: str, context: str) -> str:
        """构造问答 prompt"""
        return prompts.format_qa_prompt(query, context)

    @staticmethod
    def parse_citations(response: str) -> List[Dict[str, Any]]:
        """
        从 LLM 响应中解析引用

        格式：[文档ID §节号]、[文档ID] 或 [文档ID | 文件名 §节号 P页码]

        Args:
            response: LLM 响应

        Returns:
            引用列表
        """
        citations = []
        for raw_label in re.findall(r"\[([^\[\]]+?)\]", response):
            label = raw_label.strip()
            doc_part = label.split("|", 1)[0].strip()
            doc_id = re.split(r"\s*§", doc_part, maxsplit=1)[0].strip()
            section_match = re.search(r"§\s*([^\s\]|]+)", label)
            section = section_match.group(1).strip() if section_match else ""

            if doc_id:
                citations.append({
                    "doc_id": doc_id,
                    "section": section,
                    "type": "inline"
                })

        # 去重
        unique_citations = []
        seen = set()
        for citation in citations:
            key = (citation["doc_id"], citation["section"])
            if key not in seen:
                unique_citations.append(citation)
                seen.add(key)

        return unique_citations
