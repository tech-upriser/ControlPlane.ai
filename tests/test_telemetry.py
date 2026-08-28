import json
import pytest
from app.core.telemetry import AuditLogger, AuditEvent, RuleTriggered


@pytest.fixture
def logger():
    return AuditLogger(buffer_size=1000)


def _make_event(session_id="test-session", final_action="allow", turn=1, tokens=100):
    """Helper to create a basic AuditEvent."""
    return AuditEvent(
        session_id=session_id,
        request_id="req-001",
        policy_profile="default",
        latency_overhead_ms=5.2,
        checkers_executed=["pii_scanner", "injection_detector"],
        rules_triggered=[],
        risk_scores={"performance": 95, "cost": 100, "responsibility": 90},
        final_action=final_action,
        context_health_score=85.0,
        turn_number=turn,
        token_count_delta=tokens,
    )


def test_log_event_stored_in_buffer(logger):
    """Log event - stored in ring buffer."""
    event = _make_event()
    event_hash = logger.log_event(event)
    assert len(logger.get_recent(50)) == 1
    assert isinstance(event_hash, str)
    assert len(event_hash) == 64  # SHA-256 hex digest


def test_hash_chain_integrity(logger):
    """Hash chain - event.prev_hash matches SHA-256 of previous event."""
    event1 = _make_event(turn=1)
    hash1 = logger.log_event(event1)

    event2 = _make_event(turn=2)
    hash2 = logger.log_event(event2)

    events = logger.get_recent(50)
    assert events[0].prev_hash == "GENESIS"  # First event chains from GENESIS
    assert events[1].prev_hash == hash1  # Second event chains from first's hash
    assert hash1 != hash2  # Different events produce different hashes


def test_ring_buffer_overflow(logger):
    """Ring buffer overflow - after 1001 events, buffer still has 1000."""
    small_logger = AuditLogger(buffer_size=1000)
    for i in range(1001):
        event = _make_event(turn=i)
        small_logger.log_event(event)

    events = small_logger.get_recent(1100)
    assert len(events) == 1000  # Capped at buffer size


def test_get_recent_returns_last_n(logger):
    """get_recent(5) - returns last 5 events in chronological order."""
    for i in range(10):
        event = _make_event(turn=i, tokens=i * 10)
        logger.log_event(event)

    recent = logger.get_recent(5)
    assert len(recent) == 5
    # Should be chronological (turn 5, 6, 7, 8, 9)
    assert recent[0].turn_number == 5
    assert recent[-1].turn_number == 9


def test_no_raw_pii_in_log(logger):
    """No raw PII in log - assert no credit card numbers or SSNs in serialized JSON."""
    rule = RuleTriggered(
        checker="pii_scanner",
        category="CREDIT_CARD",
        action_taken="redacted",
        confidence=1.0,
    )
    event = _make_event()
    event.rules_triggered = [rule]
    logger.log_event(event)

    events = logger.get_recent(1)
    serialized = events[0].model_dump_json()

    # Should NOT contain actual PII values
    assert "4111-1111-1111-1111" not in serialized
    assert "123-45-6789" not in serialized
    # Should contain category metadata only
    assert "CREDIT_CARD" in serialized
    assert "redacted" in serialized


def test_create_event_factory(logger):
    """create_event factory method produces valid AuditEvent."""
    rule = RuleTriggered(
        checker="injection_detector",
        category="direct_injection",
        action_taken="blocked",
        confidence=0.95,
    )
    event = logger.create_event(
        session_id="raw-session-id-123",
        request_id="req-factory-001",
        policy_profile="customer_support",
        latency_ms=12.5,
        checkers=["injection_detector"],
        rules=[rule],
        risk_scores={"performance": 100, "cost": 100, "responsibility": 20},
        final_action="block",
        health_score=75.0,
        turn=3,
        tokens=250,
    )
    assert event.policy_profile == "customer_support"
    assert event.final_action == "block"
    assert event.turn_number == 3
    # Session ID should be hashed, not raw
    assert event.session_id != "raw-session-id-123"
    assert len(event.session_id) == 16  # Truncated hash
