from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.infrastructure.db import create_session_factory


def get_session() -> Iterator[Session]:
    factory = create_session_factory(get_settings().database_url)
    session = factory()
    try:
        yield session
    finally:
        session.close()
