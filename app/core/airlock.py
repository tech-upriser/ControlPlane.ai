import uuid
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException

from app.core.policy import PolicyProfile


router = APIRouter()


@dataclass
class ToolCallRequest:
    """Represents a pending tool call awaiting approval."""
    request_id: str
    tool_name: str
    tool_args: dict
    session_id: str
    status: str = "pending"  # "pending", "approved", "denied"
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None


class AirLockGate:
    """Tool-call safety gate with approval/denial flow."""

    def __init__(self):
        self._pending: Dict[str, ToolCallRequest] = {}

    def check_tool_call(
        self, tool_name: str, tool_args: dict, policy: PolicyProfile, session_id: str = ""
    ) -> dict:
        """
        Check if a tool call is allowed by the policy.

        Returns:
            dict with keys:
                - "allowed": bool
                - "action": "allow" | "blocked" | "pending_approval"
                - "request_id": str (if pending)
                - "reason": str
        """
        # If policy blocks all tool calls
        if policy.tool_call_action == "block":
            return {
                "allowed": False,
                "action": "blocked",
                "request_id": None,
                "reason": f"Tool calls are blocked by policy '{policy.name}'",
            }

        # If tool is in restricted list
        if tool_name in policy.restricted_tools:
            if policy.tool_call_action == "require_approval":
                # Create pending approval request
                request_id = str(uuid.uuid4())
                request = ToolCallRequest(
                    request_id=request_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    session_id=session_id,
                )
                self._pending[request_id] = request
                return {
                    "allowed": False,
                    "action": "pending_approval",
                    "request_id": request_id,
                    "reason": f"Tool '{tool_name}' requires approval (restricted by policy '{policy.name}')",
                }
            else:
                # Block by default if restricted
                return {
                    "allowed": False,
                    "action": "blocked",
                    "request_id": None,
                    "reason": f"Tool '{tool_name}' is restricted by policy '{policy.name}'",
                }

        # Tool is allowed
        return {
            "allowed": True,
            "action": "allow",
            "request_id": None,
            "reason": "Tool call permitted",
        }

    def approve(self, request_id: str) -> ToolCallRequest:
        """Approve a pending tool call request."""
        request = self._pending.get(request_id)
        if request is None:
            raise KeyError(f"Request not found: {request_id}")
        if request.status != "pending":
            raise ValueError(f"Request already resolved: {request.status}")

        request.status = "approved"
        request.resolved_at = time.time()
        return request

    def deny(self, request_id: str) -> ToolCallRequest:
        """Deny a pending tool call request."""
        request = self._pending.get(request_id)
        if request is None:
            raise KeyError(f"Request not found: {request_id}")
        if request.status != "pending":
            raise ValueError(f"Request already resolved: {request.status}")

        request.status = "denied"
        request.resolved_at = time.time()
        return request

    def get_request(self, request_id: str) -> Optional[ToolCallRequest]:
        """Get a tool call request by ID."""
        return self._pending.get(request_id)

    def get_pending(self) -> List[ToolCallRequest]:
        """Get all pending tool call requests."""
        return [r for r in self._pending.values() if r.status == "pending"]

    def cleanup_old(self, max_age_seconds: int = 300) -> int:
        """Remove resolved or expired requests. Returns count removed."""
        now = time.time()
        to_remove = [
            rid for rid, req in self._pending.items()
            if req.status != "pending" or (now - req.created_at) > max_age_seconds
        ]
        for rid in to_remove:
            del self._pending[rid]
        return len(to_remove)


# Module-level instance for use across the app
_airlock_gate = AirLockGate()


def get_airlock_gate() -> AirLockGate:
    """Accessor for the module-level airlock gate."""
    return _airlock_gate


# --- Airlock API Routes ---

@router.post("/v1/airlock/{request_id}/approve")
async def approve_tool_call(request_id: str):
    """Approve a pending tool call."""
    try:
        request = _airlock_gate.approve(request_id)
        return {
            "status": "approved",
            "request_id": request.request_id,
            "tool_name": request.tool_name,
            "resolved_at": request.resolved_at,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/v1/airlock/{request_id}/deny")
async def deny_tool_call(request_id: str):
    """Deny a pending tool call."""
    try:
        request = _airlock_gate.deny(request_id)
        return {
            "status": "denied",
            "request_id": request.request_id,
            "tool_name": request.tool_name,
            "resolved_at": request.resolved_at,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/v1/airlock/pending")
async def list_pending():
    """List all pending tool call approval requests."""
    pending = _airlock_gate.get_pending()
    return {
        "pending": [
            {
                "request_id": r.request_id,
                "tool_name": r.tool_name,
                "tool_args": r.tool_args,
                "session_id": r.session_id,
                "created_at": r.created_at,
            }
            for r in pending
        ],
        "count": len(pending),
    }
