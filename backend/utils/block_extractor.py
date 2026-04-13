import hashlib
import json
import os
import re
from typing import Dict, List

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

try:
    import docx
except ImportError:
    docx = None


BLOCK_INDEX_VERSION = "block-v1"
TABLE_SPLIT_ROW_THRESHOLD = 50


def _normalize_heading_segment(segment: str) -> str:
    text = "" if segment is None else str(segment)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\n\t]+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _normalize_heading_path(heading_path: List[str]) -> List[str]:
    normalized = []
    for segment in heading_path or []:
        item = _normalize_heading_segment(segment)
        if item:
            normalized.append(item)
    return normalized


def _extract_heading_level(style_name: str) -> int | None:
    normalized_style = (style_name or "").strip().lower()
    if not normalized_style:
        return None

    if not normalized_style.startswith("heading") and not normalized_style.startswith("标题"):
        return None

    match = re.search(r"(\d+)", normalized_style)
    if match:
        return max(1, int(match.group(1)))
    return 1


def _normalize_text(text: str) -> str:
    normalized = "" if text is None else str(text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip("\n")


def _normalize_block(block: Dict) -> Dict:
    normalized = dict(block)
    normalized["block_type"] = (normalized.get("block_type") or "paragraph").strip()
    normalized["heading_path"] = _normalize_heading_path(normalized.get("heading_path") or [])
    normalized["text"] = _normalize_text(normalized.get("text") or "")
    page_number = normalized.get("page_number", normalized.get("page"))
    if page_number is not None:
        try:
            normalized["page_number"] = int(page_number)
        except (TypeError, ValueError):
            normalized["page_number"] = None
    else:
        normalized["page_number"] = None
    normalized.pop("page", None)
    return normalized


def assign_block_ids(blocks: List[Dict], document_id: str, index_version: str) -> List[Dict]:
    for index, block in enumerate(blocks):
        block["block_index"] = index
        block["block_id"] = f"{document_id}:{index_version}:{index}"
    return blocks


def _hashable_block_record(block: Dict) -> Dict:
    normalized = _normalize_block(block)
    return {
        "type": normalized.get("block_type"),
        "page_number": normalized.get("page_number"),
        "heading_path": " > ".join(normalized.get("heading_path") or []),
        "text": normalized.get("text"),
    }


def compute_indexed_content_hash(blocks: List[Dict]) -> str:
    records = [_hashable_block_record(block) for block in blocks]
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _split_table_block(rows: List[str], heading_path: List[str], page_number: int = None) -> List[Dict]:
    if not rows:
        return []

    header = rows[0]
    if len(rows) <= TABLE_SPLIT_ROW_THRESHOLD:
        return [{"block_type": "table", "heading_path": list(heading_path), "page_number": page_number, "text": "\n".join(rows)}]

    chunks = []
    data_rows = rows[1:]
    rows_per_chunk = max(1, TABLE_SPLIT_ROW_THRESHOLD - 1)
    for start in range(0, len(data_rows), rows_per_chunk):
        current = [header] + data_rows[start : start + rows_per_chunk]
        chunks.append(
            {
                "block_type": "table",
                "heading_path": list(heading_path),
                "page_number": page_number,
                "text": "\n".join(current),
            }
        )
    return chunks


def _extract_docx_blocks(filepath: str) -> List[Dict]:
    if docx is None:
        raise RuntimeError("python-docx is required for .docx extraction")
    document = docx.Document(filepath)

    blocks: List[Dict] = []
    heading_stack: List[str] = []
    body = document.element.body

    for element in body.iterchildren():
        tag = element.tag.split("}")[-1]
        if tag == "p":
            para = docx.text.paragraph.Paragraph(element, document)
            text = para.text or ""
            if not text.strip():
                continue

            style_name = getattr(para.style, "name", "") or ""
            level = _extract_heading_level(style_name)
            if level is not None:
                heading_text = _normalize_heading_segment(text)
                if heading_text:
                    heading_stack = heading_stack[: level - 1]
                    heading_stack.append(heading_text)
                    blocks.append(
                        {
                            "block_type": "heading",
                            "heading_path": list(heading_stack),
                            "page_number": None,
                            "text": text,
                        }
                    )
                continue

            blocks.append(
                {
                    "block_type": "paragraph",
                    "heading_path": list(heading_stack),
                    "page_number": None,
                    "text": text,
                }
            )
        elif tag == "tbl":
            table = docx.table.Table(element, document)
            rows = []
            for row in table.rows:
                row_cells = [cell.text.strip() for cell in row.cells]
                row_line = " | ".join([cell for cell in row_cells if cell])
                if row_line:
                    rows.append(row_line)
            blocks.extend(_split_table_block(rows, heading_stack, page_number=None))

    return blocks


def _extract_pdf_blocks(filepath: str) -> List[Dict]:
    if PdfReader is None:
        raise RuntimeError("PyPDF2 is required for .pdf extraction")
    reader = PdfReader(filepath)
    blocks: List[Dict] = []

    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        normalized = _normalize_text(text)
        if not normalized:
            continue
        blocks.append(
            {
                "block_type": "paragraph",
                "heading_path": [],
                "page_number": page_index,
                "text": text,
            }
        )
    return blocks


def extract_structured_blocks(filepath: str, document_id: str) -> Dict:
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in {".docx", ".pdf"}:
        raise ValueError(f"Unsupported file type: {ext}")

    if ext == ".docx":
        blocks = _extract_docx_blocks(filepath)
    else:
        blocks = _extract_pdf_blocks(filepath)

    normalized_blocks = []
    for block in blocks:
        normalized = _normalize_block(block)
        if normalized.get("text"):
            normalized_blocks.append(normalized)
    assign_block_ids(normalized_blocks, document_id=document_id, index_version=BLOCK_INDEX_VERSION)

    return {
        "index_version": BLOCK_INDEX_VERSION,
        "indexed_content_hash": compute_indexed_content_hash(normalized_blocks),
        "blocks": normalized_blocks,
    }
