
# DocAgentRAG 检索架构设计文档

## 概述

本项目重构了检索系统，实现了一个更完善的检索架构，参考百度等搜索引擎的精确检索和模糊检索设计，结合 AI 大模型的向量检索，提供多种检索方式，有效帮助用户找到所需文件并定位到具体位置。

---

## 新架构文件结构

```
backend/
├── utils/
│   ├── search_query_parser.py  # 查询解析器（新增）
│   ├── search_engine.py       # 统一检索引擎（新增）
│   ├── retriever.py          # 原有检索实现
│   ├── smart_retrieval.py    # 智能检索增强
│   └── storage.py           # 向量存储和嵌入
├── api/
│   └── retrieval.py         # 检索 API 层
```

---

## 架构设计

### 1. 查询解析器 (search_query_parser.py)

**功能**: 支持百度式检索语法

**支持的语法：

| 语法 | 说明 | 示例 |
|--------|------|-------|
| 关键词 | 模糊匹配 | `项目报告` |
| `"精确短语"` | 精确匹配，必须包含完整短语 | `"2024年度报告"` |
| `-排除词` | 排除包含该词的文档 | `项目报告 -草稿` |
| `filetype:扩展名` | 文件类型过滤 | `财务报表 filetype:pdf` |
| `~模糊词~` | 模糊匹配（波浪线） | `~项目~报告~` |

**ParsedQuery 数据结构**:

```python
@dataclass
class ParsedQuery:
    original_query: str          # 原始查询
    exact_phrases: List[str]   # 精确短语列表
    exclude_terms: List[str]       # 排除词列表
    include_terms: List[str]       # 包含词列表
    fuzzy_terms: List[str]       # 模糊词列表
    file_types: List[str]          # 文件类型过滤
    date_range: Optional[Tuple[str, str]]  # 日期范围
    is_advanced: bool = False      # 是否为高级查询
```

---

### 2. 统一检索引擎 (search_engine.py)

**功能**: 整合多种检索方式，提供统一检索入口

**特性**:
- BM25 索引缓存，避免每次检索重新构建
- 支持多种检索策略
- 结果融合与重排序

**BM25IndexCache**:
- 计算文档集合哈希值
- 缓存 BM25 索引
- 自动失效和更新

**UnifiedSearchEngine.search() 方法支持的检索类型：

| 检索类型 | 说明 |
|----------|------|
| `keyword` | BM25 精确关键词检索 |
| `vector` | 向量语义检索 |
| `hybrid` | 混合检索（默认） |
| `smart` | 智能检索（LLM 增强） |
| `multimodal` | 多模态检索 |

---

### 3. 原有检索实现 (retriever.py)

保留了原有的检索实现，保持向后兼容性

---

### 4. 智能检索增强 (smart_retrieval.py)

保留了原有的智能检索实现，包括：
- 查询扩展
- 多查询检索
- 结果融合
- LLM 重排序

---

## 使用方式

### 启用新架构（暂未完全启用，保持向后兼容性

新架构代码已创建，但为了保持向后兼容性，目前处于注释状态。如需启用，请取消 `search_engine，取消 `search_query_parser` 和 `unified-search`API。

### 启用步骤：

1. 在 `backend/api/retrieval.py` 中：
   - 取消注释 `from utils.search_engine import get_search_engine`
   - 取消注释 `UnifiedSearchRequest` 类和 `/unified-search`、`/search-syntax-help` 端点

---

## 新检索架构优势

1. **查询解析层** - 支持百度式的检索语法（精确匹配、模糊匹配、高级语法）
2. **统一检索引擎** - 将多种检索方式统一管理
3. **BM25 索引缓存** - 避免每次检索时重新构建，提高性能
4. **结果融合与重排序** - 更智能的结果合并策略
5. **向后兼容性** - 保留原有的 API 接口，确保系统稳定运行

---

## 未来改进

1. **完善 search_engine.py 中的编码问题解决
2. **逐步启用新 API
3. **前端集成新的检索功能
4. **性能优化和缓存策略优化

