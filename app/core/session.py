import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SessionState:
    session_id: str
    turn_count: int = 0
    cumulative_tokens: int = 0
    error_count: int = 0
    recent_health_scores: List[float] = field(default_factory=list)  # last 5
    action_history_hashes: List[str] = field(default_factory=list)   # last N, hashed
    action_history_texts: List[str] = field(default_factory=list)    # last N, for loop detection
    verified_facts: List[str] = field(default_factory=list)
    key_decisions: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    tokens_wasted_on_loops: int = 0


class SessionStore:
    def __init__(self, ttl_seconds: int = 1800, max_action_history: int = 10):
        self._sessions: dict[str, SessionState] = {}
        self._ttl = ttl_seconds
        self._max_history = max_action_history

    def create_session(self, session_id: str) -> SessionState:
        """Creates a new session. Returns existing if already exists."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        session = SessionState(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Returns session state or None if not found/expired."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        # Check if session has expired
        if time.time() - session.last_active_at > self._ttl:
            del self._sessions[session_id]
            return None
        return session

    def update_session(
        self,
        session_id: str,
        token_delta: int = 0,
        had_error: bool = False,
        health_score: Optional[float] = None,
        action_text: Optional[str] = None,
        loop_tokens_wasted: int = 0,
    ) -> SessionState:
        """Increments turn count, adds tokens, updates rolling scores."""
        session = self.get_session(session_id)
        if session is None:
            session = self.create_session(session_id)

        session.turn_count += 1
        session.cumulative_tokens += token_delta
        session.last_active_at = time.time()
        session.tokens_wasted_on_loops += loop_tokens_wasted

        if had_error:
            session.error_count += 1

        if health_score is not None:
            session.recent_health_scores.append(health_score)
            # Keep only last 5 scores
            if len(session.recent_health_scores) > 5:
                session.recent_health_scores = session.recent_health_scores[-5:]

        if action_text is not None:
            # Store the text for loop detection
            session.action_history_texts.append(action_text)
            if len(session.action_history_texts) > self._max_history:
                session.action_history_texts = session.action_history_texts[-self._max_history:]

            # Store the hash for audit
            action_hash = hashlib.sha256(action_text.encode()).hexdigest()[:16]
            session.action_history_hashes.append(action_hash)
            if len(session.action_history_hashes) > self._max_history:
                session.action_history_hashes = session.action_history_hashes[-self._max_history:]

        return session

    def fork_session(self, session_id: str) -> dict:
        """Extracts clean JSON seed for a new session.
        Returns {verified_facts, key_decisions, previous_health, turn_count}."""
        session = self.get_session(session_id)
        if session is None:
            return {
                'verified_facts': [],
                'key_decisions': [],
                'previous_health': None,
                'turn_count': 0,
            }

        return {
            'verified_facts': list(session.verified_facts),
            'key_decisions': list(session.key_decisions),
            'previous_health': (
                session.recent_health_scores[-1]
                if session.recent_health_scores
                else None
            ),
            'turn_count': session.turn_count,
        }

    def add_verified_fact(self, session_id: str, fact: str) -> None:
        """Adds a human-verified fact to the session for fork extraction."""
        session = self.get_session(session_id)
        if session is None:
            session = self.create_session(session_id)
        session.verified_facts.append(fact)

    def evict_expired(self) -> int:
        """Removes sessions older than TTL. Returns count removed."""
        now = time.time()
        expired_ids = [
            sid
            for sid, session in self._sessions.items()
            if now - session.last_active_at > self._ttl
        ]
        for sid in expired_ids:
            del self._sessions[sid]
        return len(expired_ids)

    async def start_eviction_loop(self, interval: int = 60) -> None:
        """Background task that runs evict_expired() every `interval` seconds."""
        while True:
            await asyncio.sleep(interval)
            self.evict_expired()
