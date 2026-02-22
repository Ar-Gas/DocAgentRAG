import os

DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "your-doubao-api-key-here")
DOUBAO_EMBEDDING_API_URL = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"
DOUBAO_EMBEDDING_MODEL = "doubao-embedding-vision-250615"
DOUBAO_LLM_API_URL = os.getenv("DOUBAO_LLM_API_URL", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
DOUBAO_LLM_MODEL = os.getenv("DOUBAO_LLM_MODEL", "doubao-pro-32k-241115")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
