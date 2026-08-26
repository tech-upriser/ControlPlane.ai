import asyncio
import json
import time
import uuid
from typing import AsyncGenerator

async def mock_stream(model: str, messages: list) -> AsyncGenerator[str, None]:
    """Yields SSE-formatted chunks: 'data: {json}\n\n'"""
    
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    
    if model in ("mock", "mock-normal"):
        tokens = ["Hello", "!", " I'm", " Control", "Plane", ".ai", ",", 
                  " your", " AI", " safety", " middleware", ".", 
                  " How", " can", " I", " help", " you", " today", "?"]
    elif model == "mock-pii-leak":
        tokens = ["The", " customer's", " card", " is", " 4111", "-1111", 
                  "-1111", "-1111", " and", " email", " is", 
                  " john.doe@example.com", "."]
    elif model == "mock-tool-call":
        # Yield a tool_call chunk instead of content
        tokens = []
        chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0, 
                "delta": {
                    "tool_calls": [{
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": "refund_order",
                            "arguments": '{"amount": 5000}'
                        }
                    }]
                }, 
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.03)
    elif model == "mock-loop":
        tokens = ["I", " searched", " for", " the", " answer", 
                  " but", " could", " not", " find", " it", "."]
    else:
        tokens = ["Unsupported", " model", "."]
    
    for token in tokens:
        chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.03)  # 30ms realistic delay
    
    # Final chunk with finish_reason
    final = {
        "id": chunk_id, "object": "chat.completion.chunk",
        "created": int(time.time()), "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"
