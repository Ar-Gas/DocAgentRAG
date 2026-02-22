import os
from pathlib import Path
from typing import Set, Dict

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = BASE_DIR / "data"
DOC_DIR = BASE_DIR / "doc"
CHROMA_DB_PATH = BASE_DIR / "chromadb"
MODEL_DIR = Path(os.getenv("MODEL_DIR", BASE_DIR / "models" / "all-MiniLM-L6-v2"))

try:
    from api_secrets import (
        DOUBAO_API_KEY,
        DOUBAO_EMBEDDING_API_URL,
        DOUBAO_EMBEDDING_MODEL,
        DOUBAO_LLM_API_URL,
        DOUBAO_LLM_MODEL,
        OPENAI_API_KEY,
        OPENAI_BASE_URL
    )
except ImportError:
    DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "")
    DOUBAO_EMBEDDING_API_URL = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"
    DOUBAO_EMBEDDING_MODEL = "doubao-embedding-vision-250615"
    DOUBAO_LLM_API_URL = os.getenv("DOUBAO_LLM_API_URL", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
    DOUBAO_LLM_MODEL = os.getenv("DOUBAO_LLM_MODEL", "doubao-pro-32k-241115")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")

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
API_PREFIX = "/api"

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
