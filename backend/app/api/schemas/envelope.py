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
