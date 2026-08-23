from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes.chat import router as chat_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.status import router as status_router
from app.api.routes.tools import router as tools_router

app = FastAPI(title="RUACH", version="0.1.0", docs_url=None, redoc_url=None)
app.add_middleware(RequestContextMiddleware)
register_error_handlers(app)
app.include_router(health_router, prefix="/api/v1")
app.include_router(status_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(tools_router, prefix="/api/v1")


@app.on_event("startup")
def _expire_stale_approvals() -> None:
    """Startup sweep: stale PENDING approvals become EXPLICITLY EXPIRED.

    Idempotent: safe to run on every start. Failure is observable (logged,
    audit event) but must not crash startup or depend on any record
    existing (docs/13 P4 #11).
    """
    from app.api.dependencies import get_tool_engine

    try:
        expired = get_tool_engine().expire_stale_approvals()
        if expired:
            print(f"[startup] expired {expired} stale approval(s)")
    except Exception as exc:  # noqa: BLE001 - observable, non-fatal
        print(f"[startup] approval expiry sweep FAILED: {type(exc).__name__}: {exc}")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    from app.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
