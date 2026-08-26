import hashlib
import json
import uuid
import time
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()


class RuleTriggered(BaseModel):
    checker: str           # "pii_scanner", "injection_detector", etc.
    category: str          # "CREDIT_CARD", "direct_injection", "violence", etc.
    action_taken: str      # "redacted", "blocked", "flagged", "escalated"
    confidence: float      # 0.0 - 1.0


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    session_id: str                   # hashed session identifier
    request_id: str                   # UUID
    policy_profile: str               # "customer_support", "internal_analyst"
    latency_overhead_ms: float        # time spent on checks (not LLM time)
    checkers_executed: List[str]      # ["pii_scanner", "injection_detector", ...]
    rules_triggered: List[RuleTriggered]
    risk_scores: Optional[dict] = None  # {"performance": 85, "cost": 92, "responsibility": 70}
    final_action: str                 # "allow", "flag", "reword", "block", "escalate"
    context_health_score: Optional[float] = None
    turn_number: int
    token_count_delta: int
    prev_hash: str = "GENESIS"        # SHA-256 of previous log entry for tamper detection


class AuditLogger:
    def __init__(self, buffer_size: int = 1000):
        self._ring_buffer: List[AuditEvent] = []
        self._buffer_size = buffer_size
        self._prev_hash: str = "GENESIS"

    def _compute_hash(self, event: AuditEvent) -> str:
        """SHA-256 of event JSON + prev_hash for tamper detection."""
        event_json = event.model_dump_json()
        hash_input = f"{event_json}:{event.prev_hash}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def log_event(self, event: AuditEvent) -> str:
        """Computes hash chain, writes JSON to stdout via structlog, stores in ring buffer.
        Returns the hash of this event."""
        # Set the prev_hash from the chain
        event.prev_hash = self._prev_hash

        # Compute hash for this event
        event_hash = self._compute_hash(event)

        # Update the chain
        self._prev_hash = event_hash

        # Write to stdout via structlog
        logger.info(
            "audit_event",
            event_id=event.event_id,
            session_id=event.session_id,
            final_action=event.final_action,
            checkers=event.checkers_executed,
            rules_count=len(event.rules_triggered),
            event_hash=event_hash,
        )

        # Store in ring buffer
        self._ring_buffer.append(event)
        if len(self._ring_buffer) > self._buffer_size:
            self._ring_buffer = self._ring_buffer[-self._buffer_size:]

        return event_hash

    def get_recent(self, n: int = 50) -> List[AuditEvent]:
        """Returns the last N events from the ring buffer."""
        return self._ring_buffer[-n:]

    def create_event(
        self,
        session_id: str,
        request_id: str,
        policy_profile: str,
        latency_ms: float,
        checkers: List[str],
        rules: List[RuleTriggered],
        risk_scores: Optional[dict],
        final_action: str,
        health_score: Optional[float],
        turn: int,
        tokens: int,
    ) -> AuditEvent:
        """Factory method to build an AuditEvent with auto-generated fields."""
        # Hash the session_id for privacy
        hashed_session = hashlib.sha256(session_id.encode()).hexdigest()[:16]

        return AuditEvent(
            session_id=hashed_session,
            request_id=request_id,
            policy_profile=policy_profile,
            latency_overhead_ms=latency_ms,
            checkers_executed=checkers,
            rules_triggered=rules,
            risk_scores=risk_scores,
            final_action=final_action,
            context_health_score=health_score,
            turn_number=turn,
            token_count_delta=tokens,
        )
