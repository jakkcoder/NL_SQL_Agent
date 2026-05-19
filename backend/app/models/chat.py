from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(default="")
    messages: list[ChatMessage] = Field(default_factory=list)
    session_id: str | None = None
    arn_code: str | None = None
    page_limit: int | None = None
    page_offset: int | None = None


class PageMeta(BaseModel):
    limit: int
    offset: int


class ChatResponse(BaseModel):
    reply: str
    needs_clarification: bool = False
    rows: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    page: PageMeta | None = None
    status: Literal["ok", "clarification", "out_of_scope", "error"] = "ok"
