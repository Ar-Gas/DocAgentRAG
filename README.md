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
  - 本地文本嵌入模型：BAAI/bge-m3
  - 可选多模态查询接口：豆包多模态嵌入 API（仅显式多模态检索时使用）
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
│       │   ├── pages/         # 页面视图
│       │   └── router/        # 路由配置
│       ├── package.json       # NPM 依赖
│       └── vite.config.js     # Vite 配置
├── README.md                   # 项目说明
└── SEARCH_ARCHITECTURE.md     # 检索架构文档
```

## 快速开始

### 环境要求

- Python 3.12+（建议使用虚拟环境）
- Node.js 20.19+ 或 22.12+
- Tesseract OCR（可选，用于扫描版 PDF）

### 后端安装与启动

```bash
# 创建并激活虚拟环境
cd backend
python3 -m venv .venv
. .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
python main.py

# 启动生产服务器
DEV_MODE=false python main.py
```

后端服务运行在 `http://localhost:6008`

### LightRAG 服务端与 MinerU 环境准备

当前文档上传链路已经改为「DocAgentRAG 保存本地文件与元数据，LightRAG 负责异步导入知识库」。这意味着：

- `DocAgentRAG backend` 不再负责扫描版 PDF 的最终 OCR 解析。
- 如果 LightRAG 返回 `MinerU未安装`，需要安装的是 `LightRAG 服务端` 所在 Python 环境，不是 DocAgentRAG 的 `backend/.venv`。
- DocAgentRAG 启动时会做 LightRAG 健康检查，并在本地注册 `local_only` 文档，但不会替你在 LightRAG 机器上补依赖。

推荐把 LightRAG 单独部署到独立虚拟环境，例如 `/opt/lightrag/.venv`。

#### 1. 在 LightRAG 服务器准备 Python 环境

```bash
python3 -m venv /opt/lightrag/.venv
. /opt/lightrag/.venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

#### 2. 安装 LightRAG 服务端

不同部署方式的启动命令可能有差异，但至少需要安装 LightRAG 的 API 依赖。

```bash
pip install "lightrag-hku[api]"
```

如果你是从 LightRAG 仓库源码部署，请在它自己的项目目录中执行官方安装步骤，并确认实际启动进程用的是这个虚拟环境。

#### 3. 安装 MinerU / magic-pdf

扫描版 PDF 走 OCR 时，LightRAG 会依赖 MinerU。缺少它时，上传会直接失败，并返回类似下面的报错：

```text
LightRAG returned 400: {"status":"failed","message":"（扫描版PDF，MinerU处理失败：MinerU未安装，请安装后重试（pip install magic-pdf[full]））"}
```

在 `LightRAG 服务端环境` 中执行：

```bash
pip install "magic-pdf[full]"
```

如果服务器需要系统级依赖，至少要提前准备下面这些基础组件：

- `libmagic` 相关库
- 图像处理与 OCR 常见依赖
- 构建型依赖，例如 `build-essential`

Ubuntu/Debian 常见准备方式：

```bash
sudo apt update
sudo apt install -y build-essential libmagic1 libgl1 poppler-utils tesseract-ocr
```

如果你使用 CUDA 或其他推理加速环境，请按 LightRAG 与 MinerU 当前官方说明补齐对应驱动和运行时，不要混装到 DocAgentRAG 的 backend 环境里。

#### 4. 验证 MinerU 是否安装在正确环境

先进入 LightRAG 的虚拟环境，再执行：

```bash
python -c "import magic_pdf; print('magic-pdf ok')"
```

如果这里导入失败，说明 MinerU 仍然没有装进 LightRAG 运行时环境。

#### 5. 验证 LightRAG 健康检查

确认 LightRAG 服务启动后，在 DocAgentRAG 机器或 LightRAG 机器上执行：

```bash
curl http://127.0.0.1:9621/health
```

然后在 DocAgentRAG 的 `backend/.env` 或 `secrets_api.py` 对应环境中配置：

```bash
LIGHTRAG_BASE_URL=http://127.0.0.1:9621
LIGHTRAG_API_KEY=
LIGHTRAG_TIMEOUT_SECONDS=30
LIGHTRAG_ENABLED=true
```

#### 6. 生产部署提醒

- `magic-pdf[full]` 体积较大，首次部署建议单独构建镜像或单独固化 Python 环境。
- 不要只在 DocAgentRAG 后端执行 `pip install magic-pdf[full]`，那样不能解决 LightRAG 返回的 MinerU 缺失错误。
- 升级 LightRAG 或 MinerU 后，建议立即重新执行 `/health` 与扫描版 PDF 上传测试。
- 如果历史文件只存在于本地磁盘而未导入 LightRAG，可通过本文档后面的 `local_only` 批量导入 API 做补录。

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
| POST | `/api/v1/documents/upload` | 上传文档并异步提交 LightRAG |
| GET | `/api/v1/documents/` | 获取文档列表（分页） |
| GET | `/api/v1/documents/{id}` | 获取文档详情 |
| POST | `/api/v1/documents/{id}/retry-ingest` | 重试单文档导入 LightRAG |
| DELETE | `/api/v1/documents/{id}` | 删除文档 |
| GET | `/api/v1/documents/{id}/content` | 获取文档内容与分段 |
| GET | `/api/v1/documents/{id}/reader` | 获取文档阅读器文本与高亮命中 |
| GET | `/api/v1/documents/{id}/file` | 下载或预览原文件 |
| POST | `/api/v1/documents/{id}/rechunk` | 重新分片文档 |
| GET | `/api/v1/documents/{id}/chunk-status` | 获取文档分片状态 |
| POST | `/api/v1/documents/batch/rechunk` | 批量重新分片文档 |

### 管理接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/admin/document-audit` | 查看 SQLite、本地文件、遗留 JSON、LightRAG 健康状态 |
| POST | `/api/v1/admin/document-import/local-only` | 启动 `local_only` 文档限流后台批量导入 |
| GET | `/api/v1/admin/document-import/local-only` | 查询 `local_only` 批量导入任务状态 |

`POST /api/v1/admin/document-import/local-only` 请求体示例：

```json
{
  "limit": 100,
  "concurrency": 2,
  "interval_seconds": 0.5,
  "include_failed": false
}
```

字段说明：

- `limit`: 本次最多补录多少个 `local_only` 文档
- `concurrency`: 后台并发度，建议从 `1` 或 `2` 开始
- `interval_seconds`: 每个 worker 处理完一篇后额外等待的秒数，用于给 LightRAG 限流
- `include_failed`: 是否把上次失败文档一起重新导入

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
| POST | `/api/classification/category/{category}/reclassify` | 按分类批量重新分类 |
| POST | `/api/classification/category/{category}/rechunk` | 按分类批量重新分片 |
| POST | `/api/classification/multi-level/build` | 构建多级分类树 |
| GET | `/api/classification/topic-tree` | 获取动态语义主题树 |
| POST | `/api/classification/topic-tree/build` | 重建动态语义主题树 |
| POST | `/api/classification/tables/generate` | 根据检索结果生成分类表 |

## 配置说明

### 环境变量

```bash
# 嵌入模型配置
BGE_MODEL=backend/models/BAAI/bge-m3    # 默认本地文本嵌入模型目录

# 豆包 LLM 配置
DOUBAO_API_KEY=your_api_key
DOUBAO_EMBEDDING_API_URL=https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal
DOUBAO_EMBEDDING_MODEL=doubao-embedding-vision-250615   # 仅显式多模态检索接口保留
DOUBAO_LLM_API_URL=https://ark.cn-beijing.volces.com/api/v3/chat/completions
DOUBAO_MINI_LLM_MODEL=doubao-seed-2-0-mini-260215   # 默认运行模型
DOUBAO_LLM_MODEL=doubao-pro-32k-241115          # 预留高阶/备份模型，默认不启用

# 开发模式
DEV_MODE=true
```

### 本地安装 BAAI/bge-m3

项目默认使用本地 `BAAI/bge-m3` 作为文本 embedding 模型。建议在 `backend/.venv` 中执行下面的命令，将模型完整下载到项目目录：

```bash
cd backend
. .venv/bin/activate
modelscope download --model BAAI/bge-m3 --local_dir ./models/BAAI/bge-m3
```

如果你只想验证下载命令，也可以按 ModelScope 的单文件方式执行：

```bash
modelscope download --model BAAI/bge-m3 README.md --local_dir ./tmp/bge-m3
```

下载完成后，默认配置即可直接生效；如果模型存放在其他目录，设置 `BGE_MODEL=/your/local/path` 即可覆盖。

### 本地密钥文件

本地开发时请使用 `backend/secrets_api.py` 作为密钥配置源（例如 `DOUBAO_API_KEY`），并确保该文件不提交到仓库。

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
