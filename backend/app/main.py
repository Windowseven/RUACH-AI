from fastapi import FastAPI

app = FastAPI(title="RUACH", version="0.1.0")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    from app.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
