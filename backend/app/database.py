from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    pass


def _engine():
    url = settings.resolved_database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


engine = _engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns() -> None:
    """Add columns introduced after the first local database was created."""
    additions = {
        "scholarships": {
            "source_url": "VARCHAR(1000) DEFAULT ''",
            "status": "VARCHAR(20) DEFAULT 'published'",
            "origin": "VARCHAR(20) DEFAULT 'seed'",
            "eligibility_notes": "TEXT DEFAULT ''",
            "excerpt": "TEXT DEFAULT ''",
            "fetched_at": "TIMESTAMP",
            "submitted_by": "VARCHAR(40)",
            "sections": "TEXT",
        },
        "scholarship_chunks": {"section": "VARCHAR(40) DEFAULT ''"},
        "application_plans": {"user_id": "VARCHAR(40)"},
        "advice_sessions": {"user_id": "VARCHAR(40)"},
        "users": {
            "role": "VARCHAR(20) DEFAULT 'student'",
            "firebase_uid": "VARCHAR(128)",
        },
        "user_profiles": {
            "student_level": "VARCHAR(40) DEFAULT ''",
            "institution": "VARCHAR(200) DEFAULT ''",
            "grade_level": "INTEGER",
            "stream": "VARCHAR(80) DEFAULT ''",
            "research_interest": "TEXT DEFAULT ''",
            "prior_field": "VARCHAR(120) DEFAULT ''",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in additions.items():
            if not inspector.has_table(table):
                continue
            present = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in present:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
        if inspector.has_table("users"):
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_firebase_uid ON users (firebase_uid)")
            )
