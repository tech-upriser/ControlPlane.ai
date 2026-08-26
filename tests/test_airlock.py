import pytest
from app.core.airlock import AirLockGate, ToolCallRequest
from app.core.policy import PolicyProfile


@pytest.fixture
def gate():
    return AirLockGate()


@pytest.fixture
def permissive_policy():
    """Policy that allows all tool calls."""
    return PolicyProfile(name="permissive", tool_call_action="allow", restricted_tools=[])


@pytest.fixture
def strict_policy():
    """Policy that requires approval for restricted tools."""
    return PolicyProfile(
        name="strict",
        tool_call_action="require_approval",
        restricted_tools=["refund_order", "delete_db_row", "send_email"],
    )


@pytest.fixture
def blocking_policy():
    """Policy that blocks all tool calls."""
    return PolicyProfile(name="blocking", tool_call_action="block", restricted_tools=[])


def test_unrestricted_tool_allowed(gate, permissive_policy):
    """Unrestricted tool with permissive policy -> allowed."""
    result = gate.check_tool_call("get_weather", {"city": "Tokyo"}, permissive_policy)
    assert result["allowed"] is True
    assert result["action"] == "allow"


def test_restricted_tool_requires_approval(gate, strict_policy):
    """Restricted tool with strict policy -> pending approval."""
    result = gate.check_tool_call(
        "refund_order", {"amount": 5000}, strict_policy, session_id="sess-1"
    )
    assert result["allowed"] is False
    assert result["action"] == "pending_approval"
    assert result["request_id"] is not None

    # Verify request is in pending list
    pending = gate.get_pending()
    assert len(pending) == 1
    assert pending[0].tool_name == "refund_order"


def test_non_restricted_tool_with_strict_policy(gate, strict_policy):
    """Non-restricted tool with strict policy -> allowed."""
    result = gate.check_tool_call("get_weather", {"city": "Tokyo"}, strict_policy)
    assert result["allowed"] is True
    assert result["action"] == "allow"


def test_blocking_policy_blocks_all(gate, blocking_policy):
    """Any tool call with blocking policy -> blocked."""
    result = gate.check_tool_call("get_weather", {"city": "Tokyo"}, blocking_policy)
    assert result["allowed"] is False
    assert result["action"] == "blocked"


def test_approve_flow(gate, strict_policy):
    """Approve pending request -> status becomes approved."""
    result = gate.check_tool_call(
        "delete_db_row", {"row_id": 42}, strict_policy, session_id="sess-2"
    )
    request_id = result["request_id"]

    approved = gate.approve(request_id)
    assert approved.status == "approved"
    assert approved.resolved_at is not None

    # No longer in pending
    assert len(gate.get_pending()) == 0


def test_deny_flow(gate, strict_policy):
    """Deny pending request -> status becomes denied."""
    result = gate.check_tool_call(
        "send_email", {"to": "user@example.com"}, strict_policy, session_id="sess-3"
    )
    request_id = result["request_id"]

    denied = gate.deny(request_id)
    assert denied.status == "denied"
    assert denied.resolved_at is not None


def test_approve_nonexistent_raises(gate):
    """Approving a nonexistent request -> KeyError."""
    with pytest.raises(KeyError):
        gate.approve("nonexistent-id")


def test_double_approve_raises(gate, strict_policy):
    """Approving an already-resolved request -> ValueError."""
    result = gate.check_tool_call("refund_order", {"amount": 100}, strict_policy)
    request_id = result["request_id"]
    gate.approve(request_id)

    with pytest.raises(ValueError):
        gate.approve(request_id)
