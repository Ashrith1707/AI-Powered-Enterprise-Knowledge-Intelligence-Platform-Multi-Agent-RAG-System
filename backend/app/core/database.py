"""SQLAlchemy engine, session factory and FastAPI dependency."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
pool_kwargs = {} if settings.database_url.startswith("sqlite") else {
    "pool_pre_ping": True, "pool_size": 10, "max_overflow": 20,
}
engine = create_engine(settings.database_url, connect_args=connect_args, **pool_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency yielding a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called once at application startup."""
    from app import models  # noqa: F401  (registers all model classes)
    try:
        Base.metadata.create_all(bind=engine)
        from app.core.migrate import ensure_columns
        ensure_columns(engine)
    except Exception as exc:
        raise RuntimeError(
            f"Could not connect to the database at '{settings.database_url}'. "
            "If you are not running PostgreSQL, comment out DATABASE_URL in "
            "backend/.env to fall back to local SQLite."
        ) from exc
