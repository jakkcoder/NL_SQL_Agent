from fastapi import APIRouter, Request

from app.models.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request_body: ChatRequest, request: Request) -> ChatResponse:
    service = request.app.state.chat_service
    return service.handle(request_body)
