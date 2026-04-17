import re
from typing import Iterable


SPECIAL_ERROR_LABEL = "Error"
MIN_LABEL_LENGTH = 4
MAX_LABEL_LENGTH = 8

GENERIC_LABELS = {
    "文档",
    "资料",
    "主题",
    "业务",
    "管理",
    "综合主题",
    "综合",
    "其他",
    "未分类",
    "相关的",
    "相关内容",
    "文档内容",
    "文本内容",
    "邮件正文",
    "待整理",
    "待整理事项",
    "测试文档",
}

GENERIC_FRAGMENTS = (
    "文档",
    "正文",
    "一个",
    "测试",
    "相关",
    "待整理",
)

ERROR_PATTERNS = (
    r"(ocr|parser|mineru).{0,8}(失败|错误|error|fail)",
    r"(word|pdf|excel|ppt|pptx|docx|xlsx).{0,8}(失败|错误|error|fail)",
    r"(处理|解析|提取|转换|加载|读取|预览).{0,8}(失败|错误)",
    r"package not found",
    r"cannot open empty stream",
    r"file format cannot be determined",
    r"\btraceback\b",
    r"\bexception\b",
    r"\berror\b",
    r"just a moment",
    r"<!doctype html",
)

PLACEHOLDER_PATTERNS = (
    r"^pdf文档内容（使用.+提取）$",
    r"^pdf document\b",
)

NOISE_PATTERNS = (
    r"^[-\s]*第\s*\d+\s*页[-\s]*$",
    r"^[-\s\d第页]+$",
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def is_unusable_classification_text(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False

    lowered = normalized.lower()
    if any(re.search(pattern, lowered, re.I) for pattern in ERROR_PATTERNS):
        return True

    if any(re.search(pattern, lowered, re.I) for pattern in PLACEHOLDER_PATTERNS):
        return True

    if normalized.startswith("<!DOCTYPE html") or normalized.startswith("<html"):
        return True

    return False


def sanitize_classification_label(label: str) -> str:
    cleaned = normalize_text(label)
    cleaned = re.sub(r"^[\"'`【\[{（(]+|[\"'`】\]}）)]+$", "", cleaned)
    cleaned = re.sub(r"^(标签|分类|分类标签|分类结果)\s*[:：]\s*", "", cleaned)
    cleaned = cleaned.replace(" ", "")
    return cleaned.strip("：:；;，。,.")


def normalize_classification_label(label: str, *, parent_label: str | None = None) -> str | None:
    cleaned = sanitize_classification_label(label)
    if not cleaned:
        return None

    if cleaned.lower() == SPECIAL_ERROR_LABEL.lower() or is_unusable_classification_text(cleaned):
        return SPECIAL_ERROR_LABEL

    if not _is_contract_compliant_label(cleaned):
        return None

    normalized_parent = sanitize_classification_label(parent_label or "")
    if normalized_parent and cleaned == normalized_parent:
        return None

    return cleaned


def first_usable_text(texts: Iterable[str]) -> str:
    for text in texts:
        normalized = normalize_text(text)
        if not normalized or is_unusable_classification_text(normalized):
            continue
        return normalized
    return ""


def _is_contract_compliant_label(label: str) -> bool:
    if label == SPECIAL_ERROR_LABEL:
        return True
    if not (MIN_LABEL_LENGTH <= len(label) <= MAX_LABEL_LENGTH):
        return False
    if label in GENERIC_LABELS:
        return False
    if any(fragment in label for fragment in GENERIC_FRAGMENTS):
        return False
    if any(re.search(pattern, label, re.I) for pattern in NOISE_PATTERNS):
        return False
    if re.search(r"[<>/=*_`]|--", label):
        return False
    if _count_chinese_characters(label) < 2:
        return False
    return True


def _count_chinese_characters(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))
