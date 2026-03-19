"""Tests for backend.core.iam (IAMEngine / RBAC)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.core.iam import IAMEngine


# ---------------------------------------------------------------------------
# test_load_iam_yaml
# ---------------------------------------------------------------------------


def test_load_iam_yaml(iam_engine: IAMEngine) -> None:
    """Roles and users are populated after construction."""
    # roles: admin, underwriter, analyst, viewer
    assert "admin" in iam_engine._roles
    assert "underwriter" in iam_engine._roles
    assert "analyst" in iam_engine._roles
    assert "viewer" in iam_engine._roles

    # users: admin01, uw001, analyst01, user01
    assert "admin01" in iam_engine._users
    assert "uw001" in iam_engine._users
    assert "analyst01" in iam_engine._users
    assert "user01" in iam_engine._users


# ---------------------------------------------------------------------------
# test_user_exists
# ---------------------------------------------------------------------------


def test_user_exists_known(iam_engine: IAMEngine) -> None:
    """user_exists returns True for a declared user."""
    assert iam_engine.user_exists("admin01") is True
    assert iam_engine.user_exists("user01") is True


def test_user_exists_unknown(iam_engine: IAMEngine) -> None:
    """user_exists returns False for an undeclared user."""
    assert iam_engine.user_exists("ghost") is False
    assert iam_engine.user_exists("") is False


# ---------------------------------------------------------------------------
# test_get_user_roles
# ---------------------------------------------------------------------------


def test_get_user_roles_known(iam_engine: IAMEngine) -> None:
    """Correct role list returned for every declared user."""
    assert iam_engine.get_user_roles("admin01") == ["admin"]
    assert iam_engine.get_user_roles("uw001") == ["underwriter"]
    assert iam_engine.get_user_roles("analyst01") == ["analyst"]
    assert iam_engine.get_user_roles("user01") == ["viewer"]


def test_get_user_roles_unknown(iam_engine: IAMEngine) -> None:
    """Unknown user returns an empty list without raising."""
    assert iam_engine.get_user_roles("nobody") == []


# ---------------------------------------------------------------------------
# test_allowed_read_paths
# ---------------------------------------------------------------------------


def test_allowed_read_paths_includes_role_paths(iam_engine: IAMEngine) -> None:
    """Role-based read paths are present in the user's allowed set."""
    paths = iam_engine.allowed_read_paths("user01")
    assert "/Public/**" in paths


def test_allowed_read_paths_includes_own_private(iam_engine: IAMEngine) -> None:
    """Every user automatically gets /Private/<user_id>/** in read paths."""
    paths = iam_engine.allowed_read_paths("user01")
    assert "/Private/user01/**" in paths

    paths_uw = iam_engine.allowed_read_paths("uw001")
    assert "/Private/uw001/**" in paths_uw


def test_allowed_read_paths_admin_coverage(iam_engine: IAMEngine) -> None:
    """Admin read paths cover Public, Private, and Skills."""
    paths = iam_engine.allowed_read_paths("admin01")
    assert "/Public/**" in paths
    assert "/Private/**" in paths
    assert "/Skills/**" in paths


# ---------------------------------------------------------------------------
# test_allowed_write_paths
# ---------------------------------------------------------------------------


def test_allowed_write_paths_viewer_only_own_private(iam_engine: IAMEngine) -> None:
    """Viewer has no role-based write paths; only own Private is writable."""
    paths = iam_engine.allowed_write_paths("user01")
    # viewer role has write: []
    assert "/Public/**" not in paths
    assert "/Private/user01/**" in paths


def test_allowed_write_paths_analyst(iam_engine: IAMEngine) -> None:
    """Analyst can write to /Public/reports/** and own Private."""
    paths = iam_engine.allowed_write_paths("analyst01")
    assert "/Public/reports/**" in paths
    assert "/Private/analyst01/**" in paths


def test_allowed_write_paths_admin_full(iam_engine: IAMEngine) -> None:
    """Admin write paths include Public, Private, and Skills."""
    paths = iam_engine.allowed_write_paths("admin01")
    assert "/Public/**" in paths
    assert "/Private/**" in paths
    assert "/Skills/**" in paths


# ---------------------------------------------------------------------------
# test_can_read_public
# ---------------------------------------------------------------------------


def test_can_read_public_viewer(iam_engine: IAMEngine) -> None:
    """Viewer role grants read access to /Public/** paths."""
    assert iam_engine.can_read("user01", "/Public/readme.md") is True
    assert iam_engine.can_read("user01", "/Public/underwriting/guide.md") is True


def test_can_read_public_underwriter(iam_engine: IAMEngine) -> None:
    """Underwriter also has Public read access."""
    assert iam_engine.can_read("uw001", "/Public/readme.md") is True


# ---------------------------------------------------------------------------
# test_cannot_read_private_other
# ---------------------------------------------------------------------------


def test_cannot_read_private_other_user(iam_engine: IAMEngine) -> None:
    """Viewer cannot read another user's Private path via can_read."""
    # user01 (viewer) should not match /Private/uw001/**
    assert iam_engine.can_read("user01", "/Private/uw001/notes.md") is False


def test_cannot_read_private_other_analyst(iam_engine: IAMEngine) -> None:
    """Analyst role has no /Private/** read glob, so other user's private is denied."""
    assert iam_engine.can_read("analyst01", "/Private/user01/notes.md") is False


# ---------------------------------------------------------------------------
# test_can_read_own_private
# ---------------------------------------------------------------------------


def test_can_read_own_private(iam_engine: IAMEngine) -> None:
    """A user can always read their own /Private/<user_id>/** path."""
    assert iam_engine.can_read("user01", "/Private/user01/notes.md") is True
    assert iam_engine.can_read("uw001", "/Private/uw001/secret.md") is True
    assert iam_engine.can_read("analyst01", "/Private/analyst01/data.md") is True


# ---------------------------------------------------------------------------
# test_admin_can_read_all
# ---------------------------------------------------------------------------


def test_admin_can_read_all(iam_engine: IAMEngine) -> None:
    """Admin role has unrestricted read access across all top-level areas."""
    assert iam_engine.can_read("admin01", "/Public/readme.md") is True
    assert iam_engine.can_read("admin01", "/Private/user01/notes.md") is True
    assert iam_engine.can_read("admin01", "/Skills/calculate-insurance-premium.md") is True


# ---------------------------------------------------------------------------
# Reload and missing-file edge cases
# ---------------------------------------------------------------------------


def test_reload_nonexistent_file(tmp_path: Path) -> None:
    """IAMEngine remains empty (no crash) when the YAML file does not exist."""
    engine = IAMEngine(tmp_path / "missing.yaml")
    assert engine.user_exists("anyone") is False
    assert engine.get_user_roles("anyone") == []


def test_reload_updates_state(tmp_vault: Path, iam_engine: IAMEngine) -> None:
    """Calling reload() after mutating iam.yaml reflects the new state."""
    iam_path = tmp_vault / "iam.yaml"
    with open(iam_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    # Add a brand-new user
    data["users"].append({"user_id": "newbie", "roles": ["viewer"]})
    with open(iam_path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True)

    iam_engine.reload()
    assert iam_engine.user_exists("newbie") is True
    assert iam_engine.get_user_roles("newbie") == ["viewer"]
