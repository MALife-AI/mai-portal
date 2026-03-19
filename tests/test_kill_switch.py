"""Tests for backend.security.kill_switch (activate / deactivate / is_killed).

activate_kill_switch and deactivate_kill_switch are async coroutines that
acquire an asyncio.Lock internally.  All tests that invoke them are declared
as ``async def`` and run automatically by pytest-asyncio (asyncio_mode = "auto"
is configured in pyproject.toml).
"""
from __future__ import annotations

import pytest

import backend.security.kill_switch as ks


# ---------------------------------------------------------------------------
# Autouse fixture: reset kill switch state around every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def reset_kill_switch() -> None:
    """Ensure the kill switch is deactivated before and after every test."""
    await ks.deactivate_kill_switch()
    yield
    await ks.deactivate_kill_switch()


# ---------------------------------------------------------------------------
# test_initial_state
# ---------------------------------------------------------------------------


async def test_initial_state_is_inactive() -> None:
    """Kill switch starts (and resets to) inactive state."""
    assert ks.is_killed() is False


# ---------------------------------------------------------------------------
# test_activate_deactivate
# ---------------------------------------------------------------------------


async def test_activate_sets_killed_flag() -> None:
    """activate_kill_switch causes is_killed to return True."""
    await ks.activate_kill_switch()
    assert ks.is_killed() is True


async def test_deactivate_clears_killed_flag() -> None:
    """deactivate_kill_switch causes is_killed to return False."""
    await ks.activate_kill_switch()
    assert ks.is_killed() is True  # sanity check

    await ks.deactivate_kill_switch()
    assert ks.is_killed() is False


async def test_toggle_activate_deactivate_activate() -> None:
    """Multiple activate/deactivate cycles work correctly."""
    await ks.activate_kill_switch()
    assert ks.is_killed() is True

    await ks.deactivate_kill_switch()
    assert ks.is_killed() is False

    await ks.activate_kill_switch()
    assert ks.is_killed() is True


async def test_activate_is_idempotent() -> None:
    """Calling activate twice leaves the switch active."""
    await ks.activate_kill_switch()
    await ks.activate_kill_switch()
    assert ks.is_killed() is True


async def test_deactivate_is_idempotent() -> None:
    """Calling deactivate twice leaves the switch inactive."""
    await ks.deactivate_kill_switch()
    await ks.deactivate_kill_switch()
    assert ks.is_killed() is False


async def test_deactivate_without_prior_activate() -> None:
    """Deactivating an already-inactive switch does not raise."""
    # Switch is already off from the autouse fixture.
    await ks.deactivate_kill_switch()  # should be a no-op
    assert ks.is_killed() is False


# ---------------------------------------------------------------------------
# Reason parameter and status reporting
# ---------------------------------------------------------------------------


async def test_activate_with_custom_reason() -> None:
    """activate_kill_switch accepts an optional reason string."""
    await ks.activate_kill_switch(reason="Security incident")
    status = ks.get_kill_switch_status()
    assert status["active"] is True
    assert status["reason"] == "Security incident"


async def test_status_active_false_when_inactive() -> None:
    """get_kill_switch_status reports active=False when deactivated."""
    status = ks.get_kill_switch_status()
    assert status["active"] is False


async def test_status_active_true_when_active() -> None:
    """get_kill_switch_status reports active=True after activation."""
    await ks.activate_kill_switch()
    status = ks.get_kill_switch_status()
    assert status["active"] is True


async def test_activated_at_set_on_activation() -> None:
    """get_kill_switch_status includes a non-None activated_at timestamp."""
    await ks.activate_kill_switch()
    status = ks.get_kill_switch_status()
    assert status["activated_at"] is not None


async def test_activated_at_cleared_on_deactivation() -> None:
    """activated_at is None after deactivation."""
    await ks.activate_kill_switch()
    await ks.deactivate_kill_switch()
    status = ks.get_kill_switch_status()
    assert status["activated_at"] is None


# ---------------------------------------------------------------------------
# History tracking
# ---------------------------------------------------------------------------


async def test_history_records_activation() -> None:
    """kill_switch_history has an 'activated' entry after activation."""
    history_before = len(ks.kill_switch_history)
    await ks.activate_kill_switch(reason="test")
    assert len(ks.kill_switch_history) > history_before
    last = ks.kill_switch_history[-1]
    assert last["event"] == "activated"


async def test_history_records_deactivation() -> None:
    """kill_switch_history has a 'deactivated' entry after deactivation."""
    await ks.activate_kill_switch()
    history_before = len(ks.kill_switch_history)
    await ks.deactivate_kill_switch()
    assert len(ks.kill_switch_history) > history_before
    last = ks.kill_switch_history[-1]
    assert last["event"] == "deactivated"


# ---------------------------------------------------------------------------
# is_killed is synchronous (can be tested without async)
# ---------------------------------------------------------------------------


def test_is_killed_is_synchronous() -> None:
    """is_killed is a regular (non-async) function callable from sync context."""
    result = ks.is_killed()
    assert isinstance(result, bool)
