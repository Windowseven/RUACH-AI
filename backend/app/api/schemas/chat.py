from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None


class ChatResponseData(BaseModel):
    message_id: str
    conversation_id: str
    role: str
    content: str


class ChatResponse(BaseModel):
    data: ChatResponseData
    request_id: str
