import uuid
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.api.schemas import ChatCompletionRequest
from app.core.mock_llm import mock_stream
from app.core.interceptor import StreamInterceptor

router = APIRouter()

@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatCompletionRequest):
    app_state = request.app.state
    
    # Get session and policy
    headers = dict(request.headers)
    session_id = headers.get("x-controlplane-session", str(uuid.uuid4()))
    policy = app_state.policy_engine.resolve_profile(headers)
    
    # Extract original prompt
    original_prompt = ""
    for msg in reversed(body.messages):
        # Handle dict or ChatMessage object
        role = getattr(msg, 'role', None) or (msg.get('role') if isinstance(msg, dict) else None)
        content = getattr(msg, 'content', None) or (msg.get('content') if isinstance(msg, dict) else None)
        if role == "user" and content:
            original_prompt = content
            break
            
    # Initialize interceptor
    interceptor = StreamInterceptor(
        policy=policy,
        session_store=app_state.session_store,
        audit_logger=app_state.audit_logger,
        risk_engine=app_state.risk_engine,
        session_id=session_id,
        original_prompt=original_prompt,
        model=body.model
    )
    
    # Run Input Shield
    shield_result = interceptor.scan_input(body.messages)
    if shield_result.blocked:
        # Return a blocked message via SSE
        async def blocked_generator():
            chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion.chunk",
                "model": body.model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": f"[BLOCKED] {'; '.join(shield_result.reasons)}"},
                    "finish_reason": "content_filter",
                }],
                "controlplane": {"action": shield_result.action, "reasons": shield_result.reasons},
            }
            yield f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"
        
        return StreamingResponse(
            blocked_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
        )

    # Normal Stream wrapper
    raw_stream = mock_stream(body.model, body.messages)
    
    async def event_generator():
        async for chunk in interceptor.intercept_stream(raw_stream):
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
