from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.middleware import request_id_var
from app.api.schemas.envelope import ErrorBody, ErrorResponse
from app.application.inference import (
    InferenceFailed,
    InferenceRuntimeUnavailable,
    InferenceTimeout,
    ModelLoadFailed,
    ModelNotFound,
)

_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_413_CONTENT_TOO_LARGE: "PAYLOAD_TOO_LARGE",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


def _code_for(status_code: int) -> str:
    if status_code == 422:
        return "VALIDATION_ERROR"
    return _STATUS_CODES.get(status_code, f"HTTP_{status_code}")


def _error_response(status_code: int, code: str, message: str, details: list[str]) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details),
        request_id=request_id_var.get(),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            "{}: {}".format(".".join(str(part) for part in error["loc"][1:]), error["msg"])
            for error in exc.errors()
        ]
        return _error_response(422, "VALIDATION_ERROR", "Invalid request.", details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(exc.status_code, _code_for(exc.status_code), str(exc.detail), [])

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(500, "INTERNAL_ERROR", "Internal server error.", [])

    @app.exception_handler(InferenceRuntimeUnavailable)
    async def handle_runtime_unavailable(
        request: Request, exc: InferenceRuntimeUnavailable
    ) -> JSONResponse:
        return _error_response(
            503, "RUNTIME_UNAVAILABLE", "Local inference runtime is unavailable.", []
        )

    @app.exception_handler(ModelNotFound)
    async def handle_model_not_found(request: Request, exc: ModelNotFound) -> JSONResponse:
        return _error_response(503, "MODEL_NOT_FOUND", "Configured model is not available.", [])

    @app.exception_handler(ModelLoadFailed)
    async def handle_model_load_failed(request: Request, exc: ModelLoadFailed) -> JSONResponse:
        return _error_response(503, "MODEL_LOAD_FAILED", "Model failed to load.", [])

    @app.exception_handler(InferenceTimeout)
    async def handle_inference_timeout(request: Request, exc: InferenceTimeout) -> JSONResponse:
        return _error_response(504, "INFERENCE_TIMEOUT", "Inference took too long.", [])

    @app.exception_handler(InferenceFailed)
    async def handle_inference_failed(request: Request, exc: InferenceFailed) -> JSONResponse:
        return _error_response(502, "INFERENCE_FAILED", "Local inference failed.", [])
