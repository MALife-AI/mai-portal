"""긴급 차단(Kill Switch) API."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_kill_switch_active = asyncio.Event()
_lock = asyncio.Lock()

# --- State tracking --------------------------------------------------------

_kill_switch_reason: str | None = None
_activated_at: datetime | None = None
_auto_deactivate_at: datetime | None = None
_timeout_task: asyncio.Task | None = None

# History of activation/deactivation events (bounded to prevent memory leak)
from collections import deque as _deque
kill_switch_history: _deque[dict] = _deque(maxlen=1000)


def _record_event(event_type: str, reason: str | None = None) -> dict:
    """Record an activation or deactivation event with timestamp."""
    entry = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    kill_switch_history.append(entry)
    return entry


async def activate_kill_switch(reason: str = "Manual activation") -> None:
    """Activate the kill switch with a reason.

    Thread-safe via asyncio.Lock.
    """
    global _kill_switch_reason, _activated_at, _auto_deactivate_at

    async with _lock:
        _kill_switch_active.set()
        _kill_switch_reason = reason
        _activated_at = datetime.now(timezone.utc)
        _auto_deactivate_at = None
        _record_event("activated", reason)
        logger.critical("KILL SWITCH ACTIVATED -- reason: %s", reason)


async def deactivate_kill_switch(reason: str = "Manual deactivation") -> None:
    """Deactivate the kill switch.

    Thread-safe via asyncio.Lock. Also cancels any pending auto-deactivation.
    """
    global _kill_switch_reason, _activated_at, _auto_deactivate_at, _timeout_task

    async with _lock:
        _kill_switch_active.clear()
        _record_event("deactivated", reason)
        _kill_switch_reason = None
        _activated_at = None
        _auto_deactivate_at = None

        if _timeout_task is not None and not _timeout_task.done():
            _timeout_task.cancel()
            _timeout_task = None

        logger.info("Kill switch deactivated -- reason: %s", reason)


async def activate_with_timeout(seconds: int, reason: str = "Timed activation") -> None:
    """Activate the kill switch and auto-deactivate after *seconds*.

    If the kill switch is already active, this resets the timeout.
    """
    global _auto_deactivate_at, _timeout_task

    await activate_kill_switch(reason=reason)

    async with _lock:
        _auto_deactivate_at = datetime.now(timezone.utc).__class__.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + seconds, tz=timezone.utc
        )

        # Cancel any existing timeout task
        if _timeout_task is not None and not _timeout_task.done():
            _timeout_task.cancel()

        async def _auto_deactivate():
            try:
                await asyncio.sleep(seconds)
                await deactivate_kill_switch(
                    reason=f"Auto-deactivated after {seconds}s timeout"
                )
            except asyncio.CancelledError:
                pass  # Timeout was cancelled (manual deactivation or new timeout)

        _timeout_task = asyncio.create_task(_auto_deactivate())

    logger.info(
        "Kill switch will auto-deactivate in %d seconds",
        seconds,
    )


def is_killed() -> bool:
    """Return whether the kill switch is currently active."""
    return _kill_switch_active.is_set()


def get_kill_switch_status() -> dict:
    """Return current kill switch status including reason and timing info."""
    return {
        "active": _kill_switch_active.is_set(),
        "reason": _kill_switch_reason,
        "activated_at": _activated_at.isoformat() if _activated_at else None,
        "auto_deactivate_at": (
            _auto_deactivate_at.isoformat() if _auto_deactivate_at else None
        ),
    }
