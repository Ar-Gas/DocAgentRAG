"""LLM Prompt 模板库 - 所有 LLM 调用的 prompt 集中管理"""

# ============ 文档入库相关 ============

EXTRACT_METADATA_PROMPT = """分析以下文档，以 JSON 格式返回：
{{
  "doc_type": "论文|报告|会议记录|合同|教材|其他",
  "summary": "3句话摘要，简洁有力",
  "key_entities": ["实体1", "实体2"],
  "key_concepts": ["核心概念1", "核心概念2"],
  "time_mentions": ["2024年Q3", "上周"],
  "action_items": ["待办1"]（如果有）,
  "questions_answered": ["这文档回答了什么问题"]
}}

文档内容（前3000字）：
{text}

请返回纯 JSON，不要其他说明。"""

EXTRACT_ENTITIES_PROMPT = """从以下文档中提取所有重要实体，返回 JSON 数组：
[
  {{
    "entity_text": "实体文本",
    "entity_type": "PERSON|ORG|CONCEPT|PLACE|TIME|PRODUCT",
    "context": "该实体所在的上下文句子"
  }}
]

文档内容（前2000字）：
{text}

仅提取最重要的实体（不超过 20 个），返回纯 JSON。"""

EXTRACT_KG_TRIPLES_PROMPT = """从以下文档中提取知识图谱三元组（主语、谓语、宾语），返回 JSON 数组：
[
  {{
    "subject": "主语（通常是人/机构/概念）",
    "predicate": "谓语/关系（如 is_author_of, develops, implements）",
    "object": "宾语"
  }}
]

文档内容（前3000字）：
{text}

提取 5-15 个最重要的三元组，返回纯 JSON。"""

# ============ 查询相关 ============

QUERY_ANALYSIS_PROMPT = """分析用户的查询，理解其真实意图，返回 JSON：
{{
  "intent": "意图类型：事实查找|文档定位|内容总结|比较分析",
  "expanded_queries": ["原始查询", "扩展查询1", "扩展查询2"],
  "entity_filters": ["要查找的实体1", "实体2"]（如果有）,
  "time_filter": "时间范围如 2024 或 null",
  "doc_type_hint": "文档类型提示如 论文 或 null"
}}

用户查询："{query}"

请返回纯 JSON，帮助优化搜索策略。"""

# ============ 分类相关 ============

CLASSIFY_ZERO_SHOT_PROMPT = """你现在是一个资深的跨国企业档案管理员。请根据以下文档的内容摘要，为其归纳出一个专业的、符合企业办公场景的语义分类标签。

要求：
1. 标签名称必须是具体的业务领域或文档类型，如：劳动合同、财务月报、前端开发规范、会议记录。
2. 绝对不能使用无意义的词汇，如：文档、正文、一个、测试、其他、相关内容。
3. 如果文档内容是不完整的错误信息、解析失败提示、OCR失败文本或网页拦截页，请输出特殊标签 "Error"。
4. 除 Error 外，标签字数控制在 4-8 个字以内，体现专业度。
5. 只返回单一标签，不要解释。

文档标题：{title}
文档摘要（前500字）：{text}"""

ARBITRATE_LABELS_PROMPT = """比较两个分类结果，选择更准确的一个，并确保最终标签符合企业档案分类规范：

1. 必须输出具体的业务领域或文档类型，如：劳动合同、财务月报、前端开发规范、会议记录。
2. 不能使用无意义的词汇，如：文档、正文、一个、测试、其他、相关内容。
3. 如果文档摘要主要是错误信息、解析失败提示、OCR失败文本或网页拦截页，输出 "Error"。
4. 除 Error 外，标签字数必须为 4-8 个字。

文档摘要：{text}

分类路径 A（基于向量聚类）：{label_a}
分类路径 B（基于 LLM 分类）：{label_b}

请返回最合适的标签，格式：{{
  "final_label": "标签",
  "confidence": 0.95,
  "reason": "选择理由"
}}"""

# ============ 重排序相关 ============

RERANK_PROMPT = """根据用户查询，对以下候选文档进行相关性排序。

用户查询："{query}"

候选文档列表：
{documents}

请返回 JSON 数组，按相关性从高到低排序，包含文档 ID 和相关性分数（0-1）。
格式：[{{"doc_id": "xxx", "score": 0.95}}, ...]"""

# ============ 问答相关 ============

RAG_QA_PROMPT = """你是一个文档助手。根据以下检索到的文档片段，回答用户的问题。
在回答时，请：
1. 仅基于提供的文档内容回答
2. 对于每个观点，标注来源文档（格式：[文档标题 §章节号]）
3. 如果不同文档有不同观点，请指出
4. 保持回答简洁但完整

用户问题：{query}

检索到的文档内容：
{context}

请进行详细、准确的回答，并标注引用来源。"""

MULTI_DOC_SUMMARY_PROMPT = """根据以下多篇文档，生成一个综合总结，指出各文档的观点差异和共识。

文档集：
{documents}

请返回 JSON：
{{
  "consensus": "多篇文档共同观点",
  "differences": ["文档A的观点", "文档B的不同观点"],
  "key_insights": ["总体洞见1", "总体洞见2"]
}}"""

# ============ 格式化辅助函数 ============

def format_extraction_prompt(text: str) -> str:
    """格式化元数据抽取 prompt"""
    return EXTRACT_METADATA_PROMPT.format(text=text[:3000])

def format_entity_extraction_prompt(text: str) -> str:
    """格式化实体抽取 prompt"""
    return EXTRACT_ENTITIES_PROMPT.format(text=text[:2000])

def format_kg_extraction_prompt(text: str) -> str:
    """格式化知识图谱抽取 prompt"""
    return EXTRACT_KG_TRIPLES_PROMPT.format(text=text[:3000])

def format_query_analysis_prompt(query: str) -> str:
    """格式化查询分析 prompt"""
    return QUERY_ANALYSIS_PROMPT.format(query=query)

def format_classify_prompt(title: str, text: str) -> str:
    """格式化分类 prompt"""
    return CLASSIFY_ZERO_SHOT_PROMPT.format(title=title, text=text[:500])

def format_arbitrate_prompt(text: str, label_a: str, label_b: str) -> str:
    """格式化仲裁 prompt"""
    return ARBITRATE_LABELS_PROMPT.format(text=text[:300], label_a=label_a, label_b=label_b)

def format_qa_prompt(query: str, context: str) -> str:
    """格式化 RAG 问答 prompt"""
    return RAG_QA_PROMPT.format(query=query, context=context)
