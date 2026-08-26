import pytest
from types import SimpleNamespace
from app.core.risk_engine import RiskEngine, RiskScores
from app.core.policy import PolicyProfile


@pytest.fixture
def engine():
    return RiskEngine()


@pytest.fixture
def default_policy():
    return PolicyProfile(name="default")


def test_clean_results_allow(engine, default_policy):
    """Clean results (nothing triggered) — overall < 30, action=allow."""
    results = {}
    scores = engine.evaluate(results, default_policy)
    assert scores.recommended_action == "allow"
    assert scores.overall_risk < 30
    assert scores.risk_level == "low"
    assert scores.performance_score == 100.0
    assert scores.cost_score == 100.0
    assert scores.responsibility_score == 100.0


def test_pii_detected_flag_or_higher(engine, default_policy):
    """PII detected — responsibility drops, action >= flag."""
    pii_matches = [SimpleNamespace(pii_type="CREDIT_CARD"), SimpleNamespace(pii_type="EMAIL")]
    results = {'pii': pii_matches}
    scores = engine.evaluate(results, default_policy)
    assert scores.responsibility_score < 100.0
    assert scores.recommended_action in ("flag", "reword", "block", "escalate")
    assert any("PII" in r for r in scores.triggered_reasons)


def test_injection_detected_block_or_higher(engine, default_policy):
    """Injection detected — responsibility drops heavily, action >= block."""
    injection = SimpleNamespace(is_injection=True, confidence=0.95)
    results = {'injection': injection}
    scores = engine.evaluate(results, default_policy)
    assert scores.responsibility_score <= 20.0
    assert scores.recommended_action in ("flag", "reword", "block", "escalate")
    assert any("injection" in r.lower() for r in scores.triggered_reasons)


def test_combined_triggers_escalate(engine, default_policy):
    """Loop + PII + hallucination — all 3 scores drop, action=escalate."""
    pii_matches = [
        SimpleNamespace(pii_type="CREDIT_CARD"),
        SimpleNamespace(pii_type="SSN"),
        SimpleNamespace(pii_type="EMAIL"),
    ]
    injection = SimpleNamespace(is_injection=True, confidence=0.9)
    hallucination = SimpleNamespace(overall_risk="high")
    loop = SimpleNamespace(is_loop=True)
    cost = SimpleNamespace(cost_rating="wasteful")

    results = {
        'pii': pii_matches,
        'injection': injection,
        'hallucination': hallucination,
        'loop': loop,
        'cost': cost,
    }
    scores = engine.evaluate(results, default_policy)
    assert scores.performance_score < 100.0
    assert scores.cost_score < 100.0
    assert scores.responsibility_score < 100.0
    assert scores.recommended_action == "escalate"
    assert scores.risk_level == "critical"


def test_cost_only_issue(engine, default_policy):
    """Only cost issue (loop) — cost drops, performance and responsibility stay high."""
    loop = SimpleNamespace(is_loop=True)
    results = {'loop': loop}
    scores = engine.evaluate(results, default_policy)
    assert scores.cost_score < 100.0
    assert scores.performance_score == 100.0
    assert scores.responsibility_score == 100.0
    assert any("loop" in r.lower() for r in scores.triggered_reasons)
