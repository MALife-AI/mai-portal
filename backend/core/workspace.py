"""Workspace Manager: Public/Private 물리 분리 + Dynamic ACL."""
from __future__ import annotations

from fastapi import HTTPException

from backend.core.iam import IAMEngine


def enforce_workspace_acl(
    iam: IAMEngine,
    user_id: str,
    rel_path: str,
    mode: str = "read",
) -> None:
    """경로 접근 권한 검증. IAM 권한이 없는 타인의 Private 접근 시 차단."""
    checker = iam.can_read if mode == "read" else iam.can_write

    # IAM에 해당 경로 권한이 있으면 통과 (admin 등)
    if checker(user_id, rel_path):
        return

    # Private 영역은 본인만 접근 가능 (IAM 권한 없는 경우)
    parts = rel_path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "Private":
        owner = parts[1]
        if owner == user_id:
            return
        raise HTTPException(status_code=403, detail="Access denied: private workspace")

    raise HTTPException(status_code=403, detail=f"No {mode} permission for {rel_path}")
