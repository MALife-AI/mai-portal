"""Tests for vault API security helpers."""
import re
from pathlib import Path

import pytest


def test_git_hash_validation():
    """Git commit hash regex 검증."""
    pattern = re.compile(r"^[0-9a-fA-F]{4,40}$")
    assert pattern.fullmatch("abc123ef")
    assert pattern.fullmatch("1234567890abcdef1234567890abcdef12345678")
    assert not pattern.fullmatch("abc")  # too short
    assert not pattern.fullmatch("--help")
    assert not pattern.fullmatch("abc; rm -rf /")
    assert not pattern.fullmatch("abc123\nef")


def test_safe_vault_path(tmp_path: Path):
    """Path traversal 방어."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "Shared").mkdir()
    (vault_root / "Shared" / "test.md").write_text("test")

    # 정상 경로
    full = (vault_root / "Shared/test.md").resolve()
    assert full.is_relative_to(vault_root.resolve())

    # 탈출 시도
    escaped = (vault_root / "../../etc/passwd").resolve()
    assert not escaped.is_relative_to(vault_root.resolve())
