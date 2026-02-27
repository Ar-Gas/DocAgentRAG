# DocAgentRAG - 办公文档智能分类与检索系统

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Ar-Gas/DocAgentRAG)

基于 RAG (Retrieval-Augmented Generation) 技术的办公文档智能管理系统，提供文档上传、智能分类、语义检索、多模态搜索等功能。

## 核心功能

- **文档管理**：支持上传和管理多种格式的办公文档
- **智能分类**：自动识别文档类型并进行多级分类（内容 → 类型 → 时间）
- **向量检索**：基于语义相似度的智能文档检索
- **混合检索**：结合向量检索与 BM25 关键词精确匹配
- **多模态检索**：支持文本+图片联合查询
- **智能检索**：LLM 查询扩展 + 多查询融合 + 结果重排序
- **OCR 支持**：扫描版 PDF 文字识别
- **内容提炼**：噪音过滤、语义分段、层次结构构建

## 支持的文档格式

| 类型 | 扩展名 |
|------|--------|
| PDF | `.pdf` |
| Word | `.docx`, `.doc` |
| Excel | `.xlsx`, `.xls` |
| PPT | `.pptx`, `.ppt` |
| 邮件 | `.eml`, `.msg` |
| 文本 | `.txt` |
| 图片 | `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp` |

## 技术栈

### 后端
- **框架**：FastAPI + Uvicorn
- **向量数据库**：ChromaDB
- **嵌入模型**：
  - 豆包多模态嵌入 API（doubao-embedding-vision）
  - 本地回退模型：BAAI/bge-small-zh-v1.5
- **重排序模型**：bge-reranker-base
- **文档处理**：PyPDF2, python-docx, openpyxl, python-pptx
- **OCR**：pytesseract + Pillow
- **分词**：jieba

### 前端
- **框架**：Vue 3 + Vite
- **UI 组件**：Element Plus
- **路由**：Vue Router
- **HTTP 客户端**：Axios

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端应用 (Vue 3)                          │
│                    http://localhost:3000                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     后端 API (FastAPI)                           │
│                    http://localhost:6008                        │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │  文档管理   │ │  智能分类   │ │  检索服务   │               │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘               │
│         │               │               │                       │
│         ▼               ▼               ▼                       │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │ 文档处理器  │ │ 内容提炼器  │ │ 检索引擎    │               │
│  │ (OCR/解析)  │ │ (去噪/分段) │ │ (向量/BM25) │               │
│  └─────────────┘ └─────────────┘ └─────────────┘               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    向量数据库 (ChromaDB)                         │
│                    本地持久化存储                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 目录结构

```
DocAgentRAG/
├── backend/                    # 后端代码
│   ├── api/                    # API 路由
│   │   ├── document.py        # 文档管理 API
│   │   ├── retrieval.py       # 检索 API
│   │   └── classification.py  # 分类 API
│   ├── utils/                  # 工具模块
│   │   ├── storage.py         # 向量存储与嵌入
│   │   ├── retriever.py       # 检索引擎
│   │   ├── smart_retrieval.py # 智能检索
│   │   ├── document_processor.py  # 文档解析
│   │   ├── content_refiner.py # 内容提炼引擎
│   │   ├── classifier.py      # 文档分类器
│   │   └── multi_level_classifier.py  # 多级分类
│   ├── data/                   # 文档元数据 (JSON)
│   ├── doc/                    # 文档存储目录
│   ├── chromadb/              # 向量数据库
│   ├── models/                 # 模型文件
│   ├── main.py                 # 应用入口
│   └── requirements.txt        # Python 依赖
├── frontend/                   # 前端代码
│   └── docagent-frontend/
│       ├── src/               # 源代码
│       │   ├── components/    # Vue 组件
│       │   ├── views/         # 页面视图
│       │   └── router/        # 路由配置
│       ├── package.json       # NPM 依赖
│       └── vite.config.js     # Vite 配置
├── README.md                   # 项目说明
└── SEARCH_ARCHITECTURE.md     # 检索架构文档
```

## 快速开始

### 环境要求

- Python 3.8+
- Node.js 20+
- Tesseract OCR（可选，用于扫描版 PDF）

### 后端安装与启动

```bash
# 安装依赖
cd backend
pip install -r requirements.txt

# 安装 Tesseract OCR (Ubuntu/Debian)
sudo apt install tesseract-ocr

# 启动开发服务器
python main.py

# 启动生产服务器
DEV_MODE=false python main.py
```

后端服务运行在 `http://localhost:6008`

### 前端安装与启动

```bash
# 安装依赖
cd frontend/docagent-frontend
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build
```

前端服务运行在 `http://localhost:3000`

## API 接口

### 文档管理

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/documents/upload` | 上传文档 |
| GET | `/api/documents/` | 获取文档列表（分页） |
| GET | `/api/documents/{id}` | 获取文档详情 |
| DELETE | `/api/documents/{id}` | 删除文档 |
| GET | `/api/documents/{id}/refine` | 获取文档提炼结果 |
| GET | `/api/documents/{id}/hierarchy` | 获取文档层次结构 |
| GET | `/api/documents/{id}/key-info` | 获取文档关键信息 |
| POST | `/api/documents/{id}/rechunk` | 重新分片文档 |

### 检索服务

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/retrieval/search` | 语义检索 |
| POST | `/api/retrieval/hybrid-search` | 混合检索（向量+BM25） |
| POST | `/api/retrieval/keyword-search` | 关键词检索（BM25） |
| POST | `/api/retrieval/smart-search` | 智能检索（LLM 增强） |
| POST | `/api/retrieval/multimodal-search` | 多模态检索 |
| POST | `/api/retrieval/search-with-highlight` | 带高亮的检索 |

### 文档分类

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/classification/classify` | 单文档分类 |
| POST | `/api/classification/reclassify/{id}` | 重新分类 |
| GET | `/api/classification/categories` | 获取所有分类 |
| GET | `/api/classification/documents/{category}` | 获取分类下文档 |
| POST | `/api/classification/multi-level/build` | 构建多级分类树 |

## 配置说明

### 环境变量

```bash
# 嵌入模型配置
BGE_MODEL=BAAI/bge-small-zh-v1.5    # 本地回退模型

# 豆包 API 配置（推荐）
DOUBAO_API_KEY=your_api_key
DOUBAO_EMBEDDING_API_URL=https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal
DOUBAO_EMBEDDING_MODEL=doubao-embedding-vision-250615
DOUBAO_LLM_API_URL=https://ark.cn-beijing.volces.com/api/v3/chat/completions
DOUBAO_LLM_MODEL=doubao-pro-32k-241115

# OpenAI 兼容 API（可选）
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.deepseek.com

# 开发模式
DEV_MODE=true
```

### 系统配置

在 `backend/config.py` 中可配置：

- `MAX_FILE_SIZE`: 最大文件大小（默认 500MB）
- `MAX_CHUNK_LENGTH`: 分片最大长度（默认 500 字符）
- `MIN_CHUNK_LENGTH`: 分片最小长度（默认 5 字符）
- `PDF_PAGE_LIMIT`: PDF 页数限制（默认 1000 页）

## 检索功能详解

### 1. 语义检索 (Vector Search)

使用向量嵌入进行语义相似度匹配，适合查找语义相关的文档。

```bash
GET /api/retrieval/search?query=项目报告&limit=10
```

### 2. 关键词检索 (BM25)

使用 BM25 算法进行精确关键词匹配，适合精确查找。

```bash
POST /api/retrieval/keyword-search
{
  "query": "财务报表",
  "limit": 10
}
```

### 3. 混合检索 (Hybrid Search)

结合向量检索和 BM25，可调节权重。

```bash
POST /api/retrieval/hybrid-search
{
  "query": "项目报告",
  "limit": 10,
  "alpha": 0.5,
  "use_rerank": true
}
```

- `alpha`: 向量检索权重（0-1），1-alpha 为 BM25 权重

### 4. 智能检索 (Smart Search)

完整的 RAG 优化流程：查询扩展 → 多查询检索 → 结果融合 → LLM 重排序

```bash
POST /api/retrieval/smart-search
{
  "query": "项目报告",
  "limit": 10,
  "use_query_expansion": true,
  "use_llm_rerank": true,
  "expansion_method": "llm"
}
```

### 5. 多模态检索

支持文本+图片联合查询：

```bash
POST /api/retrieval/multimodal-search
{
  "query": "产品截图",
  "image_url": "https://example.com/image.png",
  "limit": 10
}
```

## 内容提炼系统

文档上传后自动进行内容提炼：

1. **噪音过滤**：移除页眉页脚、空白行、重复段落
2. **语义分段**：识别标题层级，智能分段
3. **层次构建**：构建文档目录结构
4. **分块优化**：基于语义的分块策略

## 部署建议

### 开发环境

```bash
# 后端
python main.py

# 前端
npm run dev
```

### 生产环境

```bash
# 后端
DEV_MODE=false python main.py

# 前端
npm run build
# 使用 nginx 或其他服务器托管 dist 目录
```

### Docker 部署（推荐）

```dockerfile
# 示例 Dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .

# 安装 Tesseract
RUN apt-get update && apt-get install -y tesseract-ocr

CMD ["python", "main.py"]
```

## 常见问题

### Q: OCR 处理失败？

确保已安装 Tesseract OCR：
```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr

# macOS
brew install tesseract
```

### Q: 模型加载失败？

首次运行会自动下载嵌入模型，确保网络连接正常。如下载失败，可手动下载模型到 `backend/models/` 目录。

### Q: ChromaDB 初始化错误？

这是正常现象，服务仍可正常运行。如果问题持续，删除 `backend/chromadb/` 目录重新初始化。

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
