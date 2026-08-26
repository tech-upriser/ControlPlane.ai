from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.api.schemas import ChatCompletionRequest
from app.core.mock_llm import mock_stream

router = APIRouter()

@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatCompletionRequest):
    
    async def event_generator():
        async for chunk in mock_stream(body.model, body.messages):
            if await request.is_disconnected():
                break
            yield chunk
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
