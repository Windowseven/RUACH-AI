from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None


class PendingApprovalOut(BaseModel):
    approval_id: str
    conversation_id: str
    tool: str
    capability: str
    arguments: dict[str, Any]


class ToolActivityOut(BaseModel):
    state: str
    capability: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatResponseData(BaseModel):
    message_id: str
    conversation_id: str
    role: str
    content: str
    tool: ToolActivityOut | None = None
    pending_approval: PendingApprovalOut | None = None


class ChatResponse(BaseModel):
    data: ChatResponseData
    request_id: str


class ApprovalDecisionRequest(BaseModel):
    approved: bool
