"""Search API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.dependencies import get_current_user, get_iam
from backend.core.iam import IAMEngine
from backend.indexer.search import secure_search

router = APIRouter()


@router.get("/")
async def search(
    q: str = Query(..., min_length=1),
    n: int = Query(10, ge=1, le=50),
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    results = secure_search(q, user_id, iam, n_results=n)
    return results
