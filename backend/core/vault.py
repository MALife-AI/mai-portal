"""Vault Manager: 파일 I/O + Git 자동 커밋."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiofiles
from git import Repo, InvalidGitRepositoryError

from backend.config import settings
from backend.core.frontmatter import synthesize_frontmatter

logger = logging.getLogger(__name__)


def _get_repo(vault_root: Path) -> Repo | None:
    try:
        return Repo(vault_root, search_parent_directories=True)
    except InvalidGitRepositoryError:
        return None


async def git_auto_commit(vault_root: Path, message: str) -> None:
    repo = _get_repo(vault_root)
    if repo is None:
        logger.warning("Vault is not a git repository – skipping commit")
        return

    def _commit():
        repo.git.add(A=True)
        if repo.is_dirty() or repo.untracked_files:
            repo.index.commit(message)
            logger.info("Git auto-commit: %s", message)

    await asyncio.to_thread(_commit)


async def read_document(rel_path: str) -> str:
    full = settings.vault_root / rel_path
    try:
        async with aiofiles.open(full, encoding="utf-8") as f:
            return await f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Document not found: {rel_path}")


async def write_document(
    rel_path: str,
    body: str,
    *,
    user_id: str,
    extra_meta: dict | None = None,
) -> Path:
    full = settings.vault_root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)

    content = synthesize_frontmatter(body, user_id=user_id, extra_meta=extra_meta)
    async with aiofiles.open(full, "w", encoding="utf-8") as f:
        await f.write(content)

    await git_auto_commit(settings.vault_root, f"[vault] update {rel_path} by {user_id}")
    return full


async def list_files(base_rel: str = "", glob_pattern: str = "**/*.md") -> list[str]:
    base = settings.vault_root / base_rel
    return [str(p.relative_to(settings.vault_root)) for p in base.glob(glob_pattern) if p.is_file()]
