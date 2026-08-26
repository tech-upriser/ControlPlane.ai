import os
from fastapi import APIRouter, HTTPException, Query

from app.core.session import SessionStore
from app.core.telemetry import AuditLogger
from app.core.policy import PolicyEngine

router = APIRouter()

# Module-level instances for local testing.
# In Phase 4 Integration, these will be replaced with proper dependency injection.
_session_store = SessionStore()
_audit_logger = AuditLogger()
_policy_engine = PolicyEngine()

# Load profiles on module import
_config_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'profiles')
if os.path.isdir(_config_dir):
    _policy_engine.load_profiles(_config_dir)


def get_session_store() -> SessionStore:
    """Accessor for the module-level session store."""
    return _session_store


def get_audit_logger() -> AuditLogger:
    """Accessor for the module-level audit logger."""
    return _audit_logger


def get_policy_engine() -> PolicyEngine:
    """Accessor for the module-level policy engine."""
    return _policy_engine


@router.get("/v1/session/{session_id}/health")
async def get_session_health(session_id: str):
    """Returns current context health score, warnings, and turn count."""
    session = _session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    health_data = {
        'session_id': session.session_id,
        'turn_count': session.turn_count,
        'cumulative_tokens': session.cumulative_tokens,
        'error_count': session.error_count,
        'recent_health_scores': session.recent_health_scores,
        'is_degraded': (
            len(session.recent_health_scores) > 0
            and session.recent_health_scores[-1] < 50.0
        ),
        'brain_rot_detected': (
            len(session.recent_health_scores) >= 5
            and sum(1 for s in session.recent_health_scores[-5:] if s < 50) >= 3
        ),
    }

    return health_data


@router.post("/v1/session/{session_id}/fork")
async def fork_session(session_id: str):
    """Triggers Smart Context Fork."""
    session = _session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    fork_data = _session_store.fork_session(session_id)
    return {'new_session_seed': fork_data}


@router.get("/v1/audit/recent")
async def get_recent_audit(limit: int = Query(default=50, le=500)):
    """Returns recent audit log entries from the ring buffer."""
    events = _audit_logger.get_recent(limit)
    return {
        'events': [event.model_dump() for event in events],
        'total_count': len(events),
    }


@router.get("/v1/profiles")
async def list_profiles():
    """Returns all loaded policy profile names and descriptions."""
    profile_names = _policy_engine.list_profiles()
    profiles = []
    for name in profile_names:
        profile = _policy_engine.get_profile(name)
        profiles.append({'name': profile.name, 'description': profile.description})
    return {'profiles': profiles}


@router.get("/v1/profiles/{name}")
async def get_profile(name: str):
    """Returns full policy profile configuration."""
    try:
        profile = _policy_engine.get_profile(name)
        return profile.model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Profile not found: {name}")
