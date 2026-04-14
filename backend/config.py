import os
from pathlib import Path
from typing import Set, Dict

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = BASE_DIR / "data"
DOC_DIR = BASE_DIR / "doc"
CHROMA_DB_PATH = BASE_DIR / "chromadb"
MODEL_DIR = Path(os.getenv("MODEL_DIR", BASE_DIR / "models" / "all-MiniLM-L6-v2"))

_secrets_api = None
try:
    import secrets_api as _secrets_api
except ModuleNotFoundError as exc:
    if exc.name != "secrets_api":
        raise


def _get_secret_or_env(name: str, default: str) -> str:
    if _secrets_api is not None:
        value = getattr(_secrets_api, name, None)
        if value is not None:
            return value
    return os.getenv(name, default)


DOUBAO_API_KEY = _get_secret_or_env("DOUBAO_API_KEY", "")
DOUBAO_EMBEDDING_API_URL = _get_secret_or_env(
    "DOUBAO_EMBEDDING_API_URL",
    "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal",
)
DOUBAO_EMBEDDING_MODEL = _get_secret_or_env("DOUBAO_EMBEDDING_MODEL", "doubao-embedding-vision-250615")
DOUBAO_LLM_API_URL = _get_secret_or_env(
    "DOUBAO_LLM_API_URL",
    "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
)
DOUBAO_MINI_LLM_MODEL = _get_secret_or_env("DOUBAO_MINI_LLM_MODEL", "doubao-seed-2-0-mini-260215")
DOUBAO_LLM_MODEL = _get_secret_or_env("DOUBAO_LLM_MODEL", "doubao-pro-32k-241115")

DOUBAO_DEFAULT_LLM_MODEL = DOUBAO_MINI_LLM_MODEL

# LLM 可用性标志（启动时由 main.py 检查后设置）
LLM_AVAILABLE: bool = bool(DOUBAO_API_KEY)

MAX_FILE_SIZE = 500 * 1024 * 1024
MAX_TEXT_LENGTH = 10 * 1024 * 1024
MAX_CHUNK_LENGTH = 500
MIN_CHUNK_LENGTH = 5
PDF_PAGE_LIMIT = 1000
EXCEL_CHUNK_SIZE = 100

ALLOWED_EXTENSIONS: Set[str] = {
    '.pdf', '.docx', '.doc', '.xlsx', '.xls',
    '.ppt', '.pptx', '.eml', '.msg', '.txt',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'
}

EXTENSION_TO_DIR: Dict[str, str] = {
    '.pdf': 'pdf',
    '.docx': 'word',
    '.doc': 'word',
    '.xlsx': 'excel',
    '.xls': 'excel',
    '.ppt': 'ppt',
    '.pptx': 'ppt',
    '.eml': 'eml',
    '.msg': 'eml',
    '.txt': 'txt',
    '.jpg': 'image',
    '.jpeg': 'image',
    '.png': 'image',
    '.gif': 'image',
    '.bmp': 'image',
    '.webp': 'image'
}

FILE_TYPE_DIRS = ['pdf', 'word', 'excel', 'ppt', 'eml', 'txt', 'image']

API_VERSION = "v1"
API_PREFIX = "/api/v1"

ERROR_CODES = {
    1001: "文档不存在",
    1002: "文档解析失败",
    1003: "文档存入向量库失败",
    1004: "文档删除失败",
    1005: "文档分类失败",
    1006: "文档尚未分类",
    2001: "不支持的文件类型",
    2002: "文件过大",
    2003: "文件不存在",
    3001: "集合不存在",
    3002: "检索失败",
}

for dir_path in [DATA_DIR, DOC_DIR, CHROMA_DB_PATH]:
    dir_path.mkdir(parents=True, exist_ok=True)
