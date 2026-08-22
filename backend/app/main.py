from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes.health import router as health_router

app = FastAPI(title="RUACH", version="0.1.0")
app.add_middleware(RequestContextMiddleware)
register_error_handlers(app)
app.include_router(health_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    from app.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
