from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationCreatedData(BaseModel):
    id: str
    title: str


class ConversationCreatedResponse(BaseModel):
    data: ConversationCreatedData
    request_id: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str


class ConversationListResponse(BaseModel):
    data: list[ConversationSummary]
    request_id: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ConversationDetailData(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageOut]


class ConversationDetailResponse(BaseModel):
    data: ConversationDetailData
    request_id: str
