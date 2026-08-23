from typing import Any

from pydantic import BaseModel, Field


class ToolCallIn(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    capability: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default="", max_length=64)


class ToolOutcomeOut(BaseModel):
    state: str
    output: Any = None
    reason: str = ""
    approval_id: str | None = None


class ToolOutcomeResponse(BaseModel):
    data: ToolOutcomeOut
    request_id: str


class CapabilityInfo(BaseModel):
    capability: str
    risk_level: int
    approval_required: bool


class ToolRegistryData(BaseModel):
    tools: list[CapabilityInfo]
    mode: str


class ToolRegistryResponse(BaseModel):
    data: ToolRegistryData
    request_id: str
