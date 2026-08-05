"""Minimal additive migrations.

create_all() only creates missing TABLES — it never adds columns to existing
ones. This helper ALTERs in the new nullable/defaulted columns so existing
dev databases (SQLite or PostgreSQL) keep working without Alembic.
"""
from sqlalchemy import inspect, text

from app.core.logging_config import get_logger

logger = get_logger("migrate")

# table -> {column: DDL type}
ADDITIVE_COLUMNS = {
    "users": {
        "password_hash": "VARCHAR(255) DEFAULT ''",
    },
    "documents": {
        "description": "TEXT DEFAULT ''",
        "tags": "TEXT DEFAULT '[]'",   # JSON stored as text; SQLAlchemy JSON handles both
    },
}


def ensure_columns(engine) -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in ADDITIVE_COLUMNS.items():
            if table not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    logger.info("Migration: added %s.%s", table, name)
