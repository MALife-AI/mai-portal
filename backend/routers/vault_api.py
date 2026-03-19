"""Vault CRUD API."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.dependencies import get_current_user, get_iam
from backend.config import settings
from backend.core.iam import IAMEngine
from backend.core.vault import read_document, write_document, list_files, git_auto_commit
from backend.core.workspace import enforce_workspace_acl

router = APIRouter()


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
    full = settings.vault_root / body.path
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

        full = settings.vault_root / rel_path
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
