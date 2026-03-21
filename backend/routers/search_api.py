"""Search API."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from backend.dependencies import get_current_user, get_iam
from backend.core.iam import IAMEngine
from backend.indexer.search import secure_search
from backend.config import settings

logger = logging.getLogger(__name__)

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


class MultiSourceRequest(BaseModel):
    query: str = Field(..., min_length=1)
    n_results: int = Field(5, ge=1, le=20)


@router.post("/multi-source")
async def multi_source_search(
    body: MultiSourceRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """멀티소스 RAG 검색 — GraphRAG + 벡터 검색 결합, 번호 매긴 출처 반환.

    에이전트가 [1], [2] 형태로 인라인 인용할 수 있도록 구조화된 컨텍스트 제공.
    """
    sources: list[dict[str, Any]] = []
    combined_context = ""

    # 1. GraphRAG 검색
    try:
        from backend.graph.store import GraphStore
        from backend.graph.graphrag import GraphRAGEngine

        persist_path = settings.vault_root / ".graph" / "knowledge_graph.json"
        store = GraphStore(persist_path=persist_path)
        engine = GraphRAGEngine(graph_store=store, iam_engine=iam)

        rag_result = await engine.search(
            query=body.query, user_id=user_id,
            user_roles=iam.get_user_roles(user_id),
            mode="hybrid", n_results=body.n_results,
        )

        # 엔티티별 출처 수집
        seen: set[str] = set()
        for e in rag_result.matched_entities + rag_result.related_entities:
            eid = e.get("id", "")
            if eid in seen:
                continue
            seen.add(eid)
            props = e.get("properties", {})
            source_paths = e.get("source_paths", [])
            sources.append({
                "index": len(sources) + 1,
                "entity": e.get("name", ""),
                "type": e.get("entity_type", ""),
                "description": props.get("description", ""),
                "documents": [p.split("/")[-1].replace(".md", "") for p in source_paths],
                "page_start": props.get("page_start"),
                "page_end": props.get("page_end"),
            })
            if len(sources) >= body.n_results:
                break

        combined_context = rag_result.combined_context or ""
    except Exception:
        logger.debug("GraphRAG search failed", exc_info=True)

    # 2. 벡터 검색 보충
    try:
        vector_results = secure_search(body.query, user_id, iam, n_results=body.n_results)
        for r in vector_results.get("results", []):
            meta = r.get("metadata", {})
            doc_path = meta.get("path", "")
            doc_title = doc_path.split("/")[-1].replace(".md", "") if doc_path else ""
            # 이미 GraphRAG에서 가져온 문서와 중복 체크
            existing_docs = {d for s in sources for d in s.get("documents", [])}
            if doc_title and doc_title not in existing_docs:
                sources.append({
                    "index": len(sources) + 1,
                    "entity": meta.get("title", doc_title),
                    "type": "document",
                    "description": (r.get("document", "") or "")[:200],
                    "documents": [doc_title],
                    "page_start": None,
                    "page_end": None,
                })
                if len(sources) >= body.n_results * 2:
                    break
    except Exception:
        logger.debug("Vector search failed", exc_info=True)

    # 3. 번호 매긴 컨텍스트 구성
    numbered_context_parts = []
    for s in sources:
        idx = s["index"]
        docs = ", ".join(s["documents"]) if s["documents"] else "unknown"
        page = ""
        if s.get("page_start"):
            page = f" (p.{s['page_start']}"
            if s.get("page_end") and s["page_end"] != s["page_start"]:
                page += f"-{s['page_end']}"
            page += ")"
        desc = s.get("description", "")
        numbered_context_parts.append(f"[{idx}] {s['entity']} — {docs}{page}\n{desc}")

    numbered_context = "\n\n".join(numbered_context_parts)

    return {
        "query": body.query,
        "sources": sources,
        "numbered_context": numbered_context,
        "combined_context": combined_context,
    }
