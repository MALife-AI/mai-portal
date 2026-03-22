"""Vault CRUD API."""
from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.dependencies import get_current_user, get_iam
from backend.config import settings
from backend.core.iam import IAMEngine
from backend.core.vault import read_document, write_document, list_files, git_auto_commit, _get_repo
from backend.core.workspace import enforce_workspace_acl

router = APIRouter()

_GIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")


def _safe_vault_path(rel_path: str) -> Path:
    """vault 내 경로가 vault_root 밖으로 나가지 않는지 검증합니다."""
    full = (settings.vault_root / rel_path).resolve()
    vault_root = settings.vault_root.resolve()
    if not full.is_relative_to(vault_root):
        raise HTTPException(403, "경로가 vault 범위를 벗어납니다")
    return full


def _validate_git_hash(commit: str) -> None:
    """git commit hash 형식을 검증합니다."""
    if not _GIT_HASH_RE.fullmatch(commit):
        raise HTTPException(400, "유효하지 않은 커밋 해시 형식입니다")


class DocumentCreate(BaseModel):
    path: str
    content: str
    metadata: dict | None = None


@router.get("/files")
async def list_vault_files(
    base: str = "",
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    all_files = await list_files(base)
    return [f for f in all_files if iam.can_read(user_id, f)]


@router.get("/doc")
async def get_document(
    path: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    enforce_workspace_acl(iam, user_id, path, mode="read")
    content = await read_document(path)
    return {"path": path, "content": content}


@router.post("/doc")
async def create_document(
    body: DocumentCreate,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    enforce_workspace_acl(iam, user_id, body.path, mode="write")
    await write_document(body.path, body.content, user_id=user_id, extra_meta=body.metadata)
    return {"status": "created", "path": body.path}


class DeleteRequest(BaseModel):
    path: str


class BulkDeleteRequest(BaseModel):
    paths: list[str]


@router.delete("/doc")
async def delete_document(
    body: DeleteRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """파일 삭제."""
    enforce_workspace_acl(iam, user_id, body.path, mode="write")
    full = _safe_vault_path(body.path)
    if not full.exists() or not full.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {body.path}")
    full.unlink()
    await git_auto_commit(settings.vault_root, f"[vault] delete {body.path} by {user_id}")
    return {"status": "deleted", "path": body.path}


@router.post("/doc/bulk-delete")
async def bulk_delete_documents(
    body: BulkDeleteRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """파일 단체 삭제 (멀티 선택)."""
    if not body.paths:
        raise HTTPException(status_code=400, detail="No paths provided")

    deleted: list[str] = []
    not_found: list[str] = []
    denied: list[str] = []

    for rel_path in body.paths:
        try:
            enforce_workspace_acl(iam, user_id, rel_path, mode="write")
        except HTTPException:
            denied.append(rel_path)
            continue

        try:
            full = _safe_vault_path(rel_path)
        except HTTPException:
            denied.append(rel_path)
            continue
        if not full.exists() or not full.is_file():
            not_found.append(rel_path)
            continue

        full.unlink()
        deleted.append(rel_path)

    if deleted:
        await git_auto_commit(
            settings.vault_root,
            f"[vault] bulk delete {len(deleted)} files by {user_id}",
        )

    return {
        "status": "completed",
        "deleted": deleted,
        "not_found": not_found,
        "denied": denied,
    }


@router.delete("/folder")
async def delete_folder(
    body: DeleteRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """폴더 삭제 (하위 전체)."""
    enforce_workspace_acl(iam, user_id, body.path, mode="write")
    full = settings.vault_root / body.path
    if not full.exists() or not full.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder not found: {body.path}")
    # vault 루트 삭제 방지
    if full.resolve() == settings.vault_root.resolve():
        raise HTTPException(status_code=400, detail="Cannot delete vault root")
    file_count = sum(1 for _ in full.rglob("*") if _.is_file())
    shutil.rmtree(full)
    await git_auto_commit(settings.vault_root, f"[vault] delete folder {body.path} ({file_count} files) by {user_id}")
    return {"status": "deleted", "path": body.path, "files_removed": file_count}


# ─── 버전 관리 (Git History) ──────────────────────────────────────────────────


@router.get("/doc/history")
async def get_document_history(
    path: str,
    limit: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """파일의 git commit 히스토리를 반환합니다."""
    enforce_workspace_acl(iam, user_id, path, mode="read")

    full = settings.vault_root / path
    if not full.exists():
        raise HTTPException(404, f"File not found: {path}")

    repo = _get_repo(settings.vault_root)
    if repo is None:
        return {"path": path, "versions": []}

    def _get_log() -> list[dict[str, Any]]:
        versions = []
        try:
            for commit in repo.iter_commits(paths=path, max_count=limit):
                versions.append({
                    "commit_hash": commit.hexsha[:8],
                    "full_hash": commit.hexsha,
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat(),
                    "timestamp": commit.committed_date,
                })
        except Exception:
            pass
        return versions

    versions = await asyncio.to_thread(_get_log)
    return {"path": path, "versions": versions}


@router.get("/doc/version")
async def get_document_at_version(
    path: str,
    commit: str = Query(..., description="커밋 해시 (short or full)"),
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """특정 커밋 시점의 파일 내용을 반환합니다."""
    _validate_git_hash(commit)
    enforce_workspace_acl(iam, user_id, path, mode="read")

    repo = _get_repo(settings.vault_root)
    if repo is None:
        raise HTTPException(400, "Vault is not a git repository")

    def _show() -> str | None:
        try:
            return repo.git.show(f"{commit}:{path}")
        except Exception:
            return None

    content = await asyncio.to_thread(_show)
    if content is None:
        raise HTTPException(404, "해당 버전을 찾을 수 없습니다")
    return {"path": path, "commit": commit, "content": content}


class RollbackRequest(BaseModel):
    path: str
    commit: str


@router.post("/doc/rollback")
async def rollback_document(
    body: RollbackRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """파일을 특정 커밋 시점으로 되돌립니다."""
    _validate_git_hash(body.commit)
    enforce_workspace_acl(iam, user_id, body.path, mode="write")

    repo = _get_repo(settings.vault_root)
    if repo is None:
        raise HTTPException(400, "Vault is not a git repository")

    def _restore() -> str | None:
        try:
            return repo.git.show(f"{body.commit}:{body.path}")
        except Exception:
            return None

    old_content = await asyncio.to_thread(_restore)
    if old_content is None:
        raise HTTPException(404, "해당 버전을 찾을 수 없습니다")

    full = settings.vault_root / body.path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(old_content, encoding="utf-8")

    await git_auto_commit(
        settings.vault_root,
        f"[vault] rollback {body.path} to {body.commit[:8]} by {user_id}",
    )

    return {"status": "rolled_back", "path": body.path, "commit": body.commit}
