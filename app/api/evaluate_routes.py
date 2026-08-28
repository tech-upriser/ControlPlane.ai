from fastapi import APIRouter, Header, Request, Depends
from pydantic import BaseModel
from typing import List, Optional

from app.core.segment_analyzer import analyze_response
from app.core.reword_engine import reword_text

router = APIRouter(prefix="/v1", tags=["Evaluate"])

class EvaluateRequest(BaseModel):
    prompt: str
    response_text: str
    session_id: Optional[str] = None
    platform: str = "chatgpt"

class RewordRequest(BaseModel):
    original_text: str
    prompt: str
    reasons: List[str] = []
    session_id: Optional[str] = None

@router.post("/evaluate")
async def evaluate_response(req: EvaluateRequest):
    analysis = analyze_response(
        prompt=req.prompt,
        response_text=req.response_text,
        session_id=req.session_id,
        platform=req.platform
    )
    
    import uuid
    
    return {
        "evaluation_id": str(uuid.uuid4()),
        "overall_confidence": analysis.overall_confidence,
        "risk_level": analysis.risk_level,
        "recommended_action": analysis.recommended_action,
        "dimensions": analysis.dimensions,
        "segments": [
            {
                "text": s.text,
                "classification": s.classification,
                "confidence": s.confidence,
                "badge": s.badge,
                "reasons": s.reasons
            } for s in analysis.segments
        ],
        "confidence_distribution": analysis.confidence_distribution
    }

@router.post("/reword")
async def reword_segment(req: RewordRequest):
    result = reword_text(
        original_text=req.original_text,
        prompt=req.prompt,
        reasons=req.reasons
    )
    return result
