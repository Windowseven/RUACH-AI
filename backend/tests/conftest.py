import pytest
from app.api.dependencies import (
    get_approval_index,
    get_inference,
    get_session,
    get_tool_engine,
)
from app.application.orchestrator import ApprovalIndex
from app.application.tools.approvals import InMemoryApprovalStore
from app.application.tools.audit import AuditLog
from app.application.tools.engine import ToolEngine
from app.application.tools.paths import WorkspaceBoundary
from app.infrastructure.db import get_engine
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
    tool_engine = ToolEngine(
        WorkspaceBoundary(workspace),
        InMemoryApprovalStore(),
        AuditLog(tmp_path / "audit.jsonl"),
    )
    approval_index = ApprovalIndex()

    app.dependency_overrides[get_inference] = lambda: StubInference()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_tool_engine] = lambda: tool_engine
    app.dependency_overrides[get_approval_index] = lambda: approval_index
    yield TestClient(app)
    app.dependency_overrides.clear()
