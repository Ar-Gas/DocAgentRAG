# DocAgentRAG 检索架构设计文档

## 概述

DocAgentRAG 实现了多层次的检索架构，支持向量语义检索、BM25 关键词检索、混合检索、智能检索和多模态检索，满足不同场景的检索需求。

## 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                         API 层 (retrieval.py)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ 语义检索 │ │ 混合检索 │ │ 智能检索 │ │多模态检索│           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
└───────┼────────────┼────────────┼────────────┼──────────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       检索引擎层 (retriever.py)                  │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │   向量检索引擎   │  │   BM25 检索引擎  │                    │
│  │ (ChromaDB Query) │  │  (关键词匹配)    │                    │
│  └────────┬─────────┘  └────────┬─────────┘                    │
│           │                     │                               │
│           ▼                     ▼                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    结果融合与重排序                       │  │
│  │  - 混合分数计算 (alpha * vector + (1-alpha) * bm25)      │  │
│  │  - Cross-Encoder 重排序                                   │  │
│  │  - 查询解析与过滤                                         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        │                     │
        ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                      智能检索层 (smart_retrieval.py)             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  查询扩展    │  │  多查询检索  │  │  LLM 重排序  │          │
│  │ (LLM/关键词) │  │ (并行检索)   │  │ (精确排序)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                      存储层 (storage.py)                         │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │  ChromaDB 存储   │  │  嵌入模型服务    │                    │
│  │  (向量数据库)    │  │ (豆包/BGE)       │                    │
│  └──────────────────┘  └──────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

## 核心模块详解

### 1. 查询解析器 (SearchQueryParser)

**文件位置**: `backend/utils/retriever.py`

**功能**: 解析百度式检索语法，支持高级搜索功能。

**支持的语法**:

| 语法 | 说明 | 示例 |
|------|------|------|
| 关键词 | 模糊匹配 | `项目报告` |
| `"精确短语"` | 精确匹配，必须包含完整短语 | `"2024年度报告"` |
| `-排除词` | 排除包含该词的文档 | `项目报告 -草稿` |
| `filetype:扩展名` | 文件类型过滤 | `财务报表 filetype:pdf` |
| `~模糊词~` | 模糊匹配 | `~项目~报告~` |

**数据结构**:

```python
@dataclass
class ParsedQuery:
    original_query: str           # 原始查询
    exact_phrases: List[str]      # 精确短语列表
    exclude_terms: List[str]      # 排除词列表
    include_terms: List[str]      # 包含词列表
    fuzzy_terms: List[str]        # 模糊词列表
    file_types: List[str]         # 文件类型过滤
    date_range: Optional[Tuple]   # 日期范围
    is_advanced: bool = False     # 是否为高级查询
```

### 2. BM25 检索引擎

**文件位置**: `backend/utils/retriever.py`

**功能**: 实现 BM25 算法进行关键词精确匹配。

**特性**:
- 支持中英文分词（jieba）
- BM25 索引缓存，避免重复构建
- 参数可调：k1=1.5, b=0.75

**核心方法**:

```python
class BM25:
    def fit(self, documents)      # 构建倒排索引
    def score(self, query, doc_idx)  # 计算单文档分数
    def search(self, query, documents, top_k)  # 搜索排序
```

**索引缓存**:

```python
def get_cached_bm25_index(documents: List[str], bm25_class):
    """
    获取缓存的 BM25 索引
    - 计算文档集合哈希值
    - 缓存命中时直接返回
    - 缓存失效时重新构建
    """
```

### 3. 向量检索引擎

**文件位置**: `backend/utils/storage.py`, `backend/utils/retriever.py`

**功能**: 使用向量嵌入进行语义相似度匹配。

**嵌入模型**:

1. **豆包多模态嵌入 API**（优先）
   - 模型: `doubao-embedding-vision-250615`
   - 支持文本 + 图片联合嵌入
   - 维度: 可变

2. **本地 BGE 模型**（回退）
   - 模型: `BAAI/bge-small-zh-v1.5`
   - 仅文本嵌入
   - 维度: 384

**核心方法**:

```python
def search_documents(query, limit=10, use_rerank=False, file_types=None)
    """向量语义检索"""

def multimodal_search(query, image_url=None, image_path=None, limit=10, file_types=None)
    """多模态检索（文本+图片）"""
```

### 4. 混合检索引擎

**文件位置**: `backend/utils/retriever.py`

**功能**: 结合向量检索和 BM25 关键词检索。

**算法**:

```
final_score = alpha * vector_score + (1 - alpha) * bm25_score
```

**参数说明**:
- `alpha`: 向量检索权重（0-1）
  - 0: 纯 BM25 关键词检索
  - 0.5: 均衡混合（推荐）
  - 1: 纯向量语义检索

**特性**:
- 支持百度式检索语法
- 精确匹配优先排序
- 可选 Cross-Encoder 重排序

### 5. 智能检索引擎

**文件位置**: `backend/utils/smart_retrieval.py`

**功能**: 完整的 RAG 优化流程。

**流程**:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  原始查询   │───▶│  查询扩展   │───▶│  多查询检索 │───▶│  结果融合   │
│             │    │  (LLM/关键词)│   │  (并行执行) │    │  (RRF算法)  │
└─────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘
                                                                │
                                                                ▼
                                                        ┌─────────────┐
                                                        │  LLM重排序  │
                                                        │  (精确排序) │
                                                        └─────────────┘
```

**查询扩展**:

```python
def expand_query_with_llm(query: str) -> List[str]:
    """使用 LLM 生成相关查询变体"""
    
def expand_query_keywords(query: str) -> List[str]:
    """基于关键词生成查询变体（无需 LLM）"""
```

**结果融合 (RRF)**:

```python
def reciprocal_rank_fusion(results_list, k=60):
    """
    倒数排名融合算法
    RRF(d) = Σ 1 / (k + rank(d))
    """
```

**LLM 重排序**:

```python
def llm_rerank(query: str, results: List[dict], top_k: int) -> List[dict]:
    """使用 LLM 对检索结果进行精确重排序"""
```

### 6. 多模态检索

**文件位置**: `backend/utils/retriever.py`

**功能**: 支持文本 + 图片联合查询。

**使用场景**:
- 以图搜文
- 文本 + 图片联合查询
- 图片相似度搜索

**API**:

```python
def hybrid_multimodal_search(
    query: str,
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
    limit: int = 10,
    alpha: float = 0.5,
    use_rerank: bool = True,
    file_types: Optional[List[str]] = None
) -> List[Dict]:
    """混合多模态检索：向量检索 + BM25 + 图片"""
```

## 检索类型对比

| 检索类型 | 适用场景 | 优点 | 缺点 |
|---------|---------|------|------|
| 语义检索 | 语义相关查询 | 理解语义，召回率高 | 无法精确匹配 |
| 关键词检索 | 精确查找 | 精确匹配，速度快 | 无语义理解 |
| 混合检索 | 通用场景 | 平衡语义和精确 | 参数需调优 |
| 智能检索 | 复杂查询 | 最高准确率 | 需要LLM，延迟高 |
| 多模态检索 | 图片相关 | 支持图片查询 | 需要多模态API |

## 关键词高亮

**功能**: 在检索结果中高亮匹配的关键词。

```python
def search_with_highlight(
    query: str, 
    search_type: str = 'hybrid',
    limit: int = 10,
    alpha: float = 0.5,
    use_rerank: bool = False,
    file_types: Optional[List[str]] = None
) -> Tuple[List[Dict], Dict]:
    """
    返回带高亮标记的检索结果
    
    返回格式:
    {
        "content_snippet": "项目<mark class='highlight'>报告</mark>...",
        "highlights": [
            {
                "keyword": "报告",
                "start": 2,
                "end": 4,
                "matched_text": "报告"
            }
        ],
        "matched_keywords": ["报告", "项目"]
    }
    """
```

## 重排序优化

### Cross-Encoder 重排序

**模型**: `bge-reranker-base`

**原理**: 使用 Cross-Encoder 对 query-document 对进行精确相关性评分。

```python
def rerank_documents(query, results, top_k=None):
    """
    使用 Cross-Encoder 重排序
    - 加载 bge-reranker-base 模型
    - 对每个 query-document 对评分
    - 按分数重新排序
    """
```

### LLM 重排序

**适用场景**: 需要最高准确率的场景。

**原理**: 使用 LLM 分析 query 与每个文档的相关性，给出精确排序。

## 性能优化

### 1. BM25 索引缓存

```python
# 缓存 BM25 索引，避免每次检索重新构建
_bm25_cache = None
_bm25_cache_hash = None
_bm25_doc_count = 0

def get_cached_bm25_index(documents, bm25_class):
    """基于文档哈希判断是否需要重建索引"""
```

### 2. 分批获取元数据

```python
def get_document_stats():
    """分批获取元数据，避免内存溢出"""
    batch_size = 1000
    for offset in range(0, total_chunks, batch_size):
        results = collection.get(
            limit=batch_size,
            offset=offset,
            include=["metadatas"]
        )
```

### 3. 嵌入模型回退机制

```python
class DoubaoEmbeddingFunction:
    """
    豆包嵌入函数，支持自动回退到本地模型
    - 优先使用豆包 API
    - 连续失败 3 次自动切换到本地 BGE 模型
    """
```

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/retrieval/search` | GET | 语义检索 |
| `/api/retrieval/hybrid-search` | POST | 混合检索 |
| `/api/retrieval/keyword-search` | POST | BM25 关键词检索 |
| `/api/retrieval/smart-search` | POST | 智能检索（LLM增强） |
| `/api/retrieval/multimodal-search` | POST | 多模态检索 |
| `/api/retrieval/multimodal-search-upload` | POST | 多模态检索（上传图片） |
| `/api/retrieval/search-with-highlight` | POST | 带高亮的检索 |
| `/api/retrieval/search-types` | GET | 获取支持的检索类型 |
| `/api/retrieval/expand-query` | GET | 查询扩展预览 |
| `/api/retrieval/llm-status` | GET | 检查 LLM 服务状态 |

## 使用建议

### 检索类型选择

1. **精确查找文件名或专业术语**: 使用 `keyword-search`
2. **语义相关查询**: 使用 `search` 或 `hybrid-search`
3. **需要最高准确率**: 使用 `smart-search`（需要配置 LLM）
4. **图片相关查询**: 使用 `multimodal-search`

### 参数调优

```python
# 混合检索权重建议
alpha = 0.5   # 均衡（推荐）
alpha = 0.7   # 偏向语义
alpha = 0.3   # 偏向关键词

# 是否启用重排序
use_rerank = True  # 追求准确率
use_rerank = False # 追求速度
```

## 未来改进

1. **统一检索入口**: 整合所有检索方式到单一 API
2. **检索语法增强**: 支持更多高级搜索语法
3. **检索结果缓存**: 对热门查询结果进行缓存
4. **异步检索**: 支持大规模并发检索请求
5. **检索日志分析**: 分析用户检索行为，优化检索策略
