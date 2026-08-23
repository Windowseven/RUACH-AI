from typing import Literal

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[str] = []


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str


class HealthData(BaseModel):
    status: str


class HealthResponse(BaseModel):
    data: HealthData
    request_id: str


class ReadinessData(BaseModel):
    status: Literal["ready", "not_ready", "degraded"]
    inference: str
    database: str


class ReadinessResponse(BaseModel):
    data: ReadinessData
    request_id: str


class SystemData(BaseModel):
    ruach_version: str
    api_version: str
    runtime_status: str
    inference: str
    database: str
    tools: str


class SystemResponse(BaseModel):
    data: SystemData
    request_id: str
