import os
import pytest
from app.core.policy import PolicyEngine, PolicyProfile


# Path to config/profiles relative to project root
CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config', 'profiles')


@pytest.fixture
def engine():
    """Creates a PolicyEngine loaded with all profiles."""
    pe = PolicyEngine()
    pe.load_profiles(CONFIG_DIR)
    return pe


def test_load_customer_support(engine):
    """Load customer_support.yaml - verify key fields."""
    profile = engine.get_profile('customer_support')
    assert profile.pii_action == 'redact'
    assert profile.max_latency_budget_ms == 50
    assert profile.content_safety_action == 'block'
    assert profile.loop_detection_window == 3


def test_load_internal_analyst(engine):
    """Load internal_analyst.yaml - verify tool controls."""
    profile = engine.get_profile('internal_analyst')
    assert profile.tool_call_action == 'require_approval'
    assert len(profile.restricted_tools) == 5
    assert 'refund_order' in profile.restricted_tools
    assert 'deploy_code' in profile.restricted_tools
    assert profile.escalation_enabled is True


def test_load_default(engine):
    """Load default.yaml - verify balanced defaults."""
    profile = engine.get_profile('default')
    assert profile.pii_action == 'redact'
    assert profile.escalation_enabled is False
    assert profile.content_safety_action == 'flag'
    assert profile.max_latency_budget_ms == 100


def test_resolve_profile_from_header(engine):
    """Resolve from header x-controlplane-profile: internal_analyst."""
    headers = {'x-controlplane-profile': 'internal_analyst'}
    profile = engine.resolve_profile(headers)
    assert profile.name == 'internal_analyst'


def test_resolve_unknown_profile_fallback(engine):
    """Unknown profile in header falls back to default."""
    headers = {'x-controlplane-profile': 'nonexistent_profile'}
    profile = engine.resolve_profile(headers)
    assert profile.name == 'default'


def test_resolve_missing_header_fallback(engine):
    """Missing header falls back to default."""
    headers = {}
    profile = engine.resolve_profile(headers)
    assert profile.name == 'default'


def test_list_profiles(engine):
    """List profiles returns all 3 profiles sorted."""
    profiles = engine.list_profiles()
    assert 'default' in profiles
    assert 'customer_support' in profiles
    assert 'internal_analyst' in profiles
    assert len(profiles) == 3
