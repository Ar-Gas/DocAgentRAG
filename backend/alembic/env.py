"""
Alembic environment configuration
对于 SQLite + 我们的 Repository 模式，迁移简化为记录数据库版本
"""
import os
from app.core.database import connect_sqlite
from pathlib import Path

def get_alembic_version():
    """获取当前迁移版本"""
    db_path = Path(os.getenv("DATA_DIR", "./data")) / "docagent.db"
    try:
        with connect_sqlite(db_path) as conn:
            cursor = conn.execute(
                "SELECT MAX(version) FROM alembic_version"
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else None
    except:
        return None

def init_alembic_version():
    """初始化 Alembic 版本表"""
    db_path = Path(os.getenv("DATA_DIR", "./data")) / "docagent.db"
    try:
        with connect_sqlite(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
    except:
        pass
