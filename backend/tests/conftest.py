import pytest
from app.api.dependencies import (
    get_inference,
    get_session,
    get_tool_engine,
)
from app.application.tools.audit import AuditLog
from app.application.tools.engine import ToolEngine
from app.application.tools.paths import WorkspaceBoundary
from app.config.settings import Settings
from app.infrastructure.approval_store_db import PersistentApprovalStore
from app.infrastructure.db import create_session_factory, get_engine
from app.infrastructure.inference_stub import StubInference
from app.infrastructure.models import Base
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def client(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    approval_store = PersistentApprovalStore(
        create_session_factory(settings.database_url),
        ttl_seconds=settings.approval_ttl_seconds,
    )
    tool_engine = ToolEngine(
        WorkspaceBoundary(workspace),
        approval_store,
        AuditLog(tmp_path / "audit.jsonl"),
    )

    app.dependency_overrides[get_inference] = lambda: StubInference()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_tool_engine] = lambda: tool_engine
    yield TestClient(app)
    app.dependency_overrides.clear()
