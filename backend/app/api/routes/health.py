from fastapi import APIRouter

from app.api.middleware import request_id_var
from app.api.schemas.envelope import HealthData, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        data=HealthData(status="ok"),
        request_id=request_id_var.get(),
    )
