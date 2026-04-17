"""
Add RAG tables - 新增 RAG 相关表

此迁移添加支持 RAG 功能的 4 张表：
- doc_entities
- qa_sessions
- kg_triples
- classification_feedback
"""

def upgrade():
    """创建 RAG 表"""
    # 此迁移为空，因为表已经在 metadata_store._initialize() 中创建
    # 这里仅作为版本记录
    pass

def downgrade():
    """不支持回滚"""
    pass
