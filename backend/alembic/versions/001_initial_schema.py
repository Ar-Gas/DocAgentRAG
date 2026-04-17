"""
Initial schema - 导出现有的 6 张表定义

此迁移记录系统启动前已存在的所有表。
"""

def upgrade():
    """记录初始 schema 版本"""
    # 此迁移为空，因为表已经在 metadata_store._initialize() 中创建
    # 这里仅作为版本记录
    pass

def downgrade():
    """不支持回滚"""
    pass
