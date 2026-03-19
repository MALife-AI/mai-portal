"""Tests for backend.core.workspace (enforce_workspace_acl)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.core.iam import IAMEngine
from backend.core.workspace import enforce_workspace_acl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def iam(tmp_vault: Path) -> IAMEngine:
    """Alias that shadows conftest iam_engine for workspace tests."""
    return IAMEngine(tmp_vault / "iam.yaml")


# ---------------------------------------------------------------------------
# test_public_access_allowed
# ---------------------------------------------------------------------------


def test_public_access_allowed_viewer(iam: IAMEngine) -> None:
    """Viewer role grants read access to /Public/** without raising."""
    # Must not raise
    enforce_workspace_acl(iam, "user01", "/Public/readme.md", mode="read")


def test_public_access_allowed_analyst(iam: IAMEngine) -> None:
    """Analyst can read public paths."""
    enforce_workspace_acl(iam, "analyst01", "/Public/readme.md", mode="read")


def test_public_access_allowed_underwriter(iam: IAMEngine) -> None:
    """Underwriter can read public paths."""
    enforce_workspace_acl(iam, "uw001", "/Public/underwriting/guide.md", mode="read")


# ---------------------------------------------------------------------------
# test_private_own_access
# ---------------------------------------------------------------------------


def test_private_own_access_user01(iam: IAMEngine) -> None:
    """User can access their own /Private/<user_id>/** without raising."""
    enforce_workspace_acl(iam, "user01", "/Private/user01/notes.md", mode="read")


def test_private_own_access_uw001(iam: IAMEngine) -> None:
    """Underwriter can access their own private workspace."""
    enforce_workspace_acl(iam, "uw001", "/Private/uw001/draft.md", mode="read")


# ---------------------------------------------------------------------------
# test_private_other_blocked
# ---------------------------------------------------------------------------


def test_private_other_blocked_viewer(iam: IAMEngine) -> None:
    """Accessing another user's Private raises HTTP 403."""
    with pytest.raises(HTTPException) as exc_info:
        enforce_workspace_acl(iam, "user01", "/Private/uw001/notes.md", mode="read")
    assert exc_info.value.status_code == 403


def test_private_other_blocked_analyst(iam: IAMEngine) -> None:
    """Analyst cannot read another user's private path."""
    with pytest.raises(HTTPException) as exc_info:
        enforce_workspace_acl(iam, "analyst01", "/Private/user01/notes.md", mode="read")
    assert exc_info.value.status_code == 403


def test_private_other_blocked_underwriter(iam: IAMEngine) -> None:
    """Underwriter cannot read admin's private notes even though both are valid users."""
    with pytest.raises(HTTPException) as exc_info:
        enforce_workspace_acl(iam, "uw001", "/Private/admin01/notes.md", mode="read")
    assert exc_info.value.status_code == 403


def test_private_other_blocked_detail_message(iam: IAMEngine) -> None:
    """403 detail message mentions 'private workspace'."""
    with pytest.raises(HTTPException) as exc_info:
        enforce_workspace_acl(iam, "user01", "/Private/admin01/secret.md", mode="read")
    assert "private workspace" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# test_write_permission_check
# ---------------------------------------------------------------------------


def test_write_permission_viewer_public_denied(iam: IAMEngine) -> None:
    """Viewer role has no write paths; writing to /Public/** must raise 403."""
    with pytest.raises(HTTPException) as exc_info:
        enforce_workspace_acl(iam, "user01", "/Public/readme.md", mode="write")
    assert exc_info.value.status_code == 403


def test_write_permission_viewer_own_private_allowed(iam: IAMEngine) -> None:
    """Viewer can always write to their own Private directory."""
    # Must not raise
    enforce_workspace_acl(iam, "user01", "/Private/user01/note.md", mode="write")


def test_write_permission_analyst_reports_allowed(iam: IAMEngine) -> None:
    """Analyst has write access to /Public/reports/**."""
    enforce_workspace_acl(iam, "analyst01", "/Public/reports/q2.md", mode="write")


def test_write_permission_analyst_public_denied(iam: IAMEngine) -> None:
    """Analyst cannot write to arbitrary /Public/** paths outside reports/."""
    with pytest.raises(HTTPException) as exc_info:
        enforce_workspace_acl(iam, "analyst01", "/Public/readme.md", mode="write")
    assert exc_info.value.status_code == 403


def test_write_permission_admin_full(iam: IAMEngine) -> None:
    """Admin can write to any path."""
    enforce_workspace_acl(iam, "admin01", "/Public/readme.md", mode="write")
    enforce_workspace_acl(iam, "admin01", "/Skills/new-skill.md", mode="write")
    enforce_workspace_acl(iam, "admin01", "/Private/admin01/notes.md", mode="write")


def test_write_permission_underwriter_underwriting_allowed(iam: IAMEngine) -> None:
    """Underwriter can write to /Public/underwriting/**."""
    enforce_workspace_acl(iam, "uw001", "/Public/underwriting/case.md", mode="write")


def test_write_permission_underwriter_reports_denied(iam: IAMEngine) -> None:
    """Underwriter cannot write to /Public/reports/**."""
    with pytest.raises(HTTPException) as exc_info:
        enforce_workspace_acl(iam, "uw001", "/Public/reports/q1.md", mode="write")
    assert exc_info.value.status_code == 403
