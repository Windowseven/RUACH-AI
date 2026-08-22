from fastapi import APIRouter

from app.api.middleware import request_id_var
from app.api.schemas.envelope import (
    ReadinessData,
    ReadinessResponse,
    SystemData,
    SystemResponse,
)
from app.application.status import (
    API_VERSION,
    database_state,
    inference_state,
    overall_status,
    package_version,
)

router = APIRouter(tags=["status"])


@router.get("/ready", response_model=ReadinessResponse)
def ready() -> ReadinessResponse:
    inference = inference_state()
    database = database_state()
    return ReadinessResponse(
        data=ReadinessData(
            status=overall_status(inference, database),
            inference=inference,
            database=database,
        ),
        request_id=request_id_var.get(),
    )


@router.get("/system", response_model=SystemResponse)
def system() -> SystemResponse:
    return SystemResponse(
        data=SystemData(
            ruach_version=package_version(),
            api_version=API_VERSION,
            runtime_status="running",
            inference=inference_state(),
            database=database_state(),
        ),
        request_id=request_id_var.get(),
    )
