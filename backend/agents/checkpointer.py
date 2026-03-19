"""SQLite Checkpointer 래퍼 + Audit Log 쿼리."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.config import settings

# ── Audit DB Schema ────────────────────────────────────────────────────────────
_CREATE_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS agent_audit_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id      TEXT    NOT NULL,
    user_id        TEXT    NOT NULL,
    step           INTEGER NOT NULL,
    skill_name     TEXT,
    input_payload  TEXT,
    output_payload TEXT,
    status         TEXT    NOT NULL,
    reasoning      TEXT,
    started_at     TEXT,
    completed_at   TEXT
)
"""

_CREATE_AUDIT_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_audit_user_id    ON agent_audit_log (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_skill_name ON agent_audit_log (skill_name)",
    "CREATE INDEX IF NOT EXISTS idx_audit_status     ON agent_audit_log (status)",
    "CREATE INDEX IF NOT EXISTS idx_audit_started_at ON agent_audit_log (started_at)",
]


def _audit_db_path() -> str:
    return str(settings.sqlite_checkpoint_path)


def _open_audit_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_audit_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Table Initialisation ───────────────────────────────────────────────────────

def init_audit_db() -> None:
    """Create the agent_audit_log table and indexes if they do not exist.

    Safe to call multiple times (idempotent).
    """
    settings.sqlite_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _open_audit_conn()
    try:
        conn.execute(_CREATE_AUDIT_TABLE)
        for idx_sql in _CREATE_AUDIT_INDEXES:
            conn.execute(idx_sql)
        conn.commit()
    finally:
        conn.close()


# ── Write ──────────────────────────────────────────────────────────────────────

def _to_json(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _record_to_tuple(record: dict[str, Any]) -> tuple:
    return (
        record.get("thread_id", ""),
        record.get("user_id", ""),
        record.get("step", 0),
        record.get("skill_name"),
        _to_json(record.get("input_payload")),
        _to_json(record.get("output_payload")),
        record.get("status", "unknown"),
        record.get("reasoning"),
        record.get("started_at"),
        record.get("completed_at"),
    )


_INSERT_SQL = """
INSERT INTO agent_audit_log
    (thread_id, user_id, step, skill_name,
     input_payload, output_payload,
     status, reasoning, started_at, completed_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def write_audit_record(record: dict[str, Any]) -> None:
    """Insert one audit record into agent_audit_log."""
    conn = _open_audit_conn()
    try:
        conn.execute(_INSERT_SQL, _record_to_tuple(record))
        conn.commit()
    finally:
        conn.close()


def write_audit_records(records: list[dict[str, Any]]) -> None:
    """Batch-insert multiple audit records in a single transaction."""
    if not records:
        return
    conn = _open_audit_conn()
    try:
        conn.executemany(_INSERT_SQL, [_record_to_tuple(r) for r in records])
        conn.commit()
    finally:
        conn.close()


# ── Query ──────────────────────────────────────────────────────────────────────

def _build_where_clause(
    user_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    skill_name: str | None = None,
    status: str | None = None,
) -> tuple[str, list[Any]]:
    """Build a parameterised WHERE clause from optional filters."""
    conditions: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        conditions.append("user_id = ?")
        params.append(user_id)
    if start_date is not None:
        conditions.append("started_at >= ?")
        params.append(start_date)
    if end_date is not None:
        conditions.append("started_at <= ?")
        params.append(end_date)
    if skill_name is not None:
        conditions.append("skill_name = ?")
        params.append(skill_name)
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def query_audit_logs(
    user_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    skill_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query agent_audit_log with optional filters and pagination."""
    db_path = settings.sqlite_checkpoint_path
    if not db_path.exists():
        return []

    where, params = _build_where_clause(user_id, start_date, end_date, skill_name, status)
    params.extend([limit, offset])

    conn = _open_audit_conn()
    try:
        cursor = conn.execute(
            f"SELECT * FROM agent_audit_log {where} "
            f"ORDER BY started_at DESC LIMIT ? OFFSET ?",
            params,
        )
        rows = [dict(r) for r in cursor.fetchall()]
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()

    return rows


def get_audit_stats(
    user_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Return aggregate statistics from agent_audit_log."""
    db_path = settings.sqlite_checkpoint_path
    if not db_path.exists():
        return {"total": 0, "success": 0, "error": 0, "success_rate": 0.0}

    where, params = _build_where_clause(user_id, start_date, end_date)

    conn = _open_audit_conn()
    try:
        cursor = conn.execute(
            f"SELECT status, COUNT(*) AS cnt FROM agent_audit_log {where} GROUP BY status",
            params,
        )
        counts: dict[str, int] = {}
        for row in cursor.fetchall():
            counts[row["status"]] = row["cnt"]
    except sqlite3.OperationalError:
        counts = {}
    finally:
        conn.close()

    total = sum(counts.values())
    success = counts.get("success", 0)
    error = counts.get("error", 0)
    success_rate = round(success / total, 4) if total > 0 else 0.0

    return {
        "total": total,
        "success": success,
        "error": error,
        "other": total - success - error,
        "success_rate": success_rate,
    }


# ── Skill Usage Stats ──────────────────────────────────────────────────────────

def get_skill_usage_stats() -> dict[str, Any]:
    """Return per-skill execution counts, success rates, and average duration.

    Duration is computed from ``started_at`` / ``completed_at`` ISO-8601 strings.
    Skills with unparseable timestamps receive ``avg_duration_seconds: null``.

    Returns:
        Dict keyed by skill name, each value containing:
            ``total``, ``success``, ``error``, ``success_rate``,
            ``avg_duration_seconds``.
    """
    db_path = settings.sqlite_checkpoint_path
    if not db_path.exists():
        return {}

    conn = _open_audit_conn()
    try:
        cursor = conn.execute(
            """
            SELECT
                skill_name,
                status,
                COUNT(*)        AS cnt,
                AVG(
                    CASE
                        WHEN started_at IS NOT NULL AND completed_at IS NOT NULL
                        THEN (
                            julianday(completed_at) - julianday(started_at)
                        ) * 86400.0
                        ELSE NULL
                    END
                ) AS avg_duration_seconds
            FROM agent_audit_log
            WHERE skill_name IS NOT NULL
            GROUP BY skill_name, status
            """,
        )
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()

    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        sname = row["skill_name"]
        if sname not in stats:
            stats[sname] = {
                "total": 0,
                "success": 0,
                "error": 0,
                "success_rate": 0.0,
                "avg_duration_seconds": None,
            }
        entry = stats[sname]
        entry["total"] += row["cnt"]
        if row["status"] == "success":
            entry["success"] += row["cnt"]
            # Use the success-row duration as the primary avg duration
            if row["avg_duration_seconds"] is not None:
                entry["avg_duration_seconds"] = round(row["avg_duration_seconds"], 3)
        elif row["status"] == "error":
            entry["error"] += row["cnt"]

    # Recompute success_rate after aggregation
    for entry in stats.values():
        total = entry["total"]
        entry["success_rate"] = round(entry["success"] / total, 4) if total > 0 else 0.0

    return stats
