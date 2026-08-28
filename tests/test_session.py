import time
import pytest
from app.core.session import SessionStore, SessionState


@pytest.fixture
def store():
    """Creates a SessionStore with short TTL for testing."""
    return SessionStore(ttl_seconds=1800, max_action_history=10)


def test_create_session(store):
    """Create session - turn=0, tokens=0, errors=0."""
    session = store.create_session('test-session-1')
    assert session.session_id == 'test-session-1'
    assert session.turn_count == 0
    assert session.cumulative_tokens == 0
    assert session.error_count == 0


def test_update_session(store):
    """Update session - turn increments, tokens accumulate."""
    store.create_session('test-session-2')
    session = store.update_session('test-session-2', token_delta=150)
    assert session.turn_count == 1
    assert session.cumulative_tokens == 150

    session = store.update_session('test-session-2', token_delta=200, had_error=True)
    assert session.turn_count == 2
    assert session.cumulative_tokens == 350
    assert session.error_count == 1


def test_health_score_rolling_window(store):
    """Health score rolling window - max 5 entries."""
    store.create_session('test-session-3')
    for i in range(7):
        store.update_session('test-session-3', health_score=float(i * 10))

    session = store.get_session('test-session-3')
    assert len(session.recent_health_scores) == 5
    # Should have the last 5 scores: 20, 30, 40, 50, 60
    assert session.recent_health_scores == [20.0, 30.0, 40.0, 50.0, 60.0]


def test_ttl_eviction(store):
    """Session created 31 min ago gets evicted."""
    session = store.create_session('expired-session')
    # Manually backdate the session
    session.last_active_at = time.time() - 1900  # 31+ minutes ago

    count = store.evict_expired()
    assert count == 1
    assert store.get_session('expired-session') is None


def test_fork_extraction(store):
    """Fork extraction returns verified_facts and key_decisions."""
    store.create_session('fork-session')
    store.add_verified_fact('fork-session', 'User prefers Python')
    store.add_verified_fact('fork-session', 'Project uses FastAPI')
    store.update_session('fork-session', token_delta=500, health_score=85.0)

    fork_data = store.fork_session('fork-session')
    assert 'User prefers Python' in fork_data['verified_facts']
    assert 'Project uses FastAPI' in fork_data['verified_facts']
    assert fork_data['previous_health'] == 85.0
    assert fork_data['turn_count'] == 1


def test_duplicate_create(store):
    """Duplicate create returns existing session, doesn't overwrite."""
    session1 = store.create_session('dup-session')
    store.update_session('dup-session', token_delta=100)

    session2 = store.create_session('dup-session')
    assert session2.cumulative_tokens == 100  # Preserved, not overwritten
    assert session2.turn_count == 1
