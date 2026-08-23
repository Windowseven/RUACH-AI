from pathlib import Path

from sqlalchemy import create_engine, event, make_url
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _default_busy_timeout_ms() -> int:
    # Imported lazily: keeps db.py importable by alembic env before app config.
    from app.config.settings import get_settings

    return get_settings().database_busy_timeout_ms

_engines: dict[str, Engine] = {}


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return
    database = url.database
    if not database or database == ":memory:":
        return
    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def get_engine(
    database_url: str, busy_timeout_ms: int | None = None
) -> Engine:
    """Engine factory.

    NOTE: busy_timeout is a short-contention mitigation only. Correctness
    comes from transaction boundaries: no write transaction may span model
    inference, tool execution, or human approval waiting (docs/13 P4 #2/#6).
    """
    if database_url not in _engines:
        _ensure_sqlite_parent_dir(database_url)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        effective_timeout = (
            busy_timeout_ms
            if busy_timeout_ms is not None
            else _default_busy_timeout_ms()
        )

        @event.listens_for(engine, "connect")
        def _apply_sqlite_pragma(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={int(effective_timeout)}")
            cursor.close()

        _engines[database_url] = engine
    return _engines[database_url]


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False)
