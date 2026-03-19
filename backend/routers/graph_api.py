"""Knowledge Graph & GraphRAG API.

All endpoints require the ``X-User-Id`` header, enforced via the
``get_current_user`` dependency.  The ``/build`` endpoint additionally
requires the ``admin`` role.

GraphStore and GraphExtractor are lazily initialised on first use so that
the application starts up quickly even when the graph snapshot is missing.

Endpoint summary
----------------
GET  /entities              — Fuzzy search entities (query, type, limit)
GET  /entity/{entity_id}    — Entity detail + immediate neighbours
GET  /entity/{entity_id}/subgraph — Subgraph for visualisation (depth param)
GET  /communities           — All community records with summaries
GET  /stats                 — Graph statistics
GET  /visualization         — Full graph for frontend rendering
POST /build                 — Rebuild graph from entire vault (admin only)
POST /build-document        — Add / refresh a single document in the graph
POST /search                — GraphRAG search (body: {query, mode, n_results})
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.iam import IAMEngine
from backend.dependencies import get_current_user, get_iam

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Lazy singletons — imported on first request to avoid startup overhead
# ---------------------------------------------------------------------------

_graph_store: Any = None
_graph_extractor: Any = None


def _get_store() -> Any:
    """Lazily import and return the module-level GraphStore singleton."""
    global _graph_store
    if _graph_store is None:
        from backend.graph.store import GraphStore  # noqa: PLC0415
        from backend.config import settings  # noqa: PLC0415

        persist_path = settings.vault_root / ".graph" / "knowledge_graph.json"
        _graph_store = GraphStore(persist_path=persist_path)
    return _graph_store


def _get_extractor() -> Any:
    """Lazily import and return the module-level GraphExtractor singleton."""
    global _graph_extractor
    if _graph_extractor is None:
        from backend.graph.extractor import GraphExtractor  # noqa: PLC0415

        _graph_extractor = GraphExtractor(graph_store=_get_store())
    return _graph_extractor


def _require_admin(user_id: str, iam: IAMEngine) -> None:
    """Raise 403 if *user_id* does not hold the ``admin`` role.

    Args:
        user_id: Requesting user ID.
        iam: Loaded IAM engine.

    Raises:
        :class:`fastapi.HTTPException`: HTTP 403 when the user is not admin.
    """
    if "admin" not in iam.get_user_roles(user_id):
        raise HTTPException(status_code=403, detail="Admin role required")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class GraphSearchRequest(BaseModel):
    """Request body for GraphRAG search.

    Attributes:
        query: Natural-language search query.
        mode: One of ``"local"``, ``"global"``, or ``"hybrid"``.
        n_results: Maximum number of vector search results to return.
    """

    query: str = Field(..., min_length=1, description="검색 쿼리")
    mode: str = Field(
        "hybrid",
        pattern=r"^(local|global|hybrid)$",
        description="검색 모드: local | global | hybrid",
    )
    n_results: int = Field(10, ge=1, le=50, description="최대 결과 수")


class BuildDocumentRequest(BaseModel):
    """Request body for single-document graph update.

    Attributes:
        rel_path: Vault-relative document path (e.g. ``/Products/m_care.md``).
    """

    rel_path: str = Field(..., description="문서 상대 경로 (예: /Products/m_care.md)")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/entities", summary="엔티티 검색")
async def search_entities(
    q: str = Query("", description="검색 쿼리"),
    type: str | None = Query(None, description="엔티티 타입 필터"),
    limit: int = Query(20, ge=1, le=100, description="최대 결과 수"),
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Search entities by fuzzy name matching.

    Args:
        q: Search query string.  Returns all entities when empty.
        type: Optional entity type filter (e.g. ``"product"``, ``"person"``).
        limit: Maximum number of results.
        user_id: Authenticated user ID (from ``X-User-Id`` header).

    Returns:
        Dict with ``entities`` list and ``total`` count.
    """
    store = _get_store()
    results = store.search_entities(query=q, entity_type=type, limit=limit)
    return {
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type,
                "mentions": e.mentions,
                "source_paths": e.source_paths,
                "properties": e.properties,
            }
            for e in results
        ],
        "total": len(results),
    }


@router.get("/entity/{entity_id}", summary="엔티티 상세 + 이웃")
async def get_entity(
    entity_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Return entity details plus its immediate (depth-1) neighbours.

    Args:
        entity_id: Unique entity identifier.
        user_id: Authenticated user ID.

    Returns:
        Dict with ``entity``, ``neighbors``, and ``relationships`` fields.

    Raises:
        :class:`fastapi.HTTPException`: HTTP 404 when entity not found.
    """
    store = _get_store()
    entity = store.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    neighbors, relationships = store.get_neighbors(entity_id, depth=1)

    return {
        "entity": {
            "id": entity.id,
            "name": entity.name,
            "type": entity.entity_type,
            "mentions": entity.mentions,
            "source_paths": entity.source_paths,
            "properties": entity.properties,
        },
        "neighbors": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type,
                "mentions": e.mentions,
            }
            for e in neighbors
        ],
        "relationships": [
            {
                "source": r.source_id,
                "target": r.target_id,
                "type": r.relation_type,
                "weight": r.weight,
                "source_path": r.source_path,
            }
            for r in relationships
        ],
    }


@router.get("/entity/{entity_id}/subgraph", summary="엔티티 서브그래프")
async def get_entity_subgraph(
    entity_id: str,
    depth: int = Query(2, ge=1, le=4, description="순회 깊이"),
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a subgraph rooted at *entity_id* for frontend visualisation.

    Args:
        entity_id: Root entity for the subgraph.
        depth: BFS traversal depth (1–4).
        user_id: Authenticated user ID.

    Returns:
        Dict with ``nodes`` and ``edges`` lists.

    Raises:
        :class:`fastapi.HTTPException`: HTTP 404 when entity not found.
    """
    store = _get_store()
    if store.get_entity(entity_id) is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    return store.get_subgraph(entity_ids=[entity_id], include_neighbors=(depth >= 1))


@router.get("/communities", summary="커뮤니티 목록")
async def list_communities(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """List all detected communities with their entity membership and summaries.

    Args:
        user_id: Authenticated user ID.

    Returns:
        Dict with ``communities`` list and ``total`` count.
    """
    store = _get_store()
    communities = store.get_communities()
    return {
        "communities": [
            {
                "id": c.id,
                "name": c.name,
                "entity_ids": c.entity_ids,
                "summary": c.summary,
                "level": c.level,
                "size": len(c.entity_ids),
            }
            for c in communities
        ],
        "total": len(communities),
    }


@router.get("/stats", summary="그래프 통계")
async def get_stats(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Return summary statistics about the knowledge graph.

    Args:
        user_id: Authenticated user ID.

    Returns:
        Dict with node count, edge count, entity type distribution, and
        relation type distribution.
    """
    store = _get_store()
    return store.get_stats()


@router.get("/visualization", summary="전체 그래프 시각화 데이터")
async def get_visualization(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the full graph as nodes + edges + communities for rendering.

    Intended for frontend graph visualisation libraries (e.g. D3, Cytoscape).
    For large graphs (>500 nodes) consider fetching per-entity subgraphs
    instead.

    Args:
        user_id: Authenticated user ID.

    Returns:
        Dict with ``nodes``, ``edges``, and ``communities`` lists.
    """
    store = _get_store()
    return store.to_visualization_data()


@router.post("/build", summary="그래프 재구축 (관리자 전용)")
async def build_graph(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """Rebuild the knowledge graph from all vault documents.

    Clears the existing graph and re-extracts entities and relationships from
    every Markdown file in the vault root.  This is a long-running operation.

    Args:
        user_id: Authenticated user ID (must have ``admin`` role).
        iam: IAM engine for role check.

    Returns:
        Build summary dict with ``files``, ``entities``, ``relationships``,
        ``communities``, and ``errors`` fields.

    Raises:
        :class:`fastapi.HTTPException`: HTTP 403 when caller is not admin.
    """
    _require_admin(user_id, iam)

    from backend.config import settings  # noqa: PLC0415

    extractor = _get_extractor()
    summary = await extractor.build_from_vault(settings.vault_root)
    logger.info("Graph rebuilt by user=%s: %s", user_id, summary)
    return {"status": "completed", **summary}


@router.post("/build-document", summary="단일 문서 그래프 추가")
async def build_document(
    body: BuildDocumentRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """Extract entities from a single vault document and add them to the graph.

    Useful for incrementally updating the graph when a document is created or
    edited without triggering a full vault rebuild.

    Args:
        body: Request body containing ``rel_path`` of the target document.
        user_id: Authenticated user ID.
        iam: IAM engine for read permission check.

    Returns:
        Dict with ``entities`` count, ``relationships`` count, and
        ``source_path``.

    Raises:
        :class:`fastapi.HTTPException`:
            - HTTP 403 when the user cannot read the document.
            - HTTP 404 when the document file does not exist on disk.
    """
    if not iam.can_read(user_id, body.rel_path):
        raise HTTPException(status_code=403, detail="Read access denied")

    from backend.config import settings  # noqa: PLC0415

    abs_path = settings.vault_root / body.rel_path.lstrip("/")
    if not abs_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {body.rel_path}",
        )

    extractor = _get_extractor()
    entities, relationships = await extractor.extract_from_file(abs_path, body.rel_path)

    # Persist updated graph state
    _get_store().save()

    return {
        "status": "ok",
        "source_path": body.rel_path,
        "entities": len(entities),
        "relationships": len(relationships),
    }


@router.post("/search", summary="GraphRAG 검색")
async def graphrag_search(
    body: GraphSearchRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """Execute a GraphRAG search combining vector retrieval and graph traversal.

    Supported modes:

    - ``"local"`` — entity-centric graph traversal, best for specific topics.
    - ``"global"`` — community-summary retrieval, best for broad overviews.
    - ``"hybrid"`` — (default) combines vector search with graph context.

    Args:
        body: Search request with ``query``, ``mode``, and ``n_results``.
        user_id: Authenticated user ID.
        iam: IAM engine for ACL filtering.

    Returns:
        Serialised :class:`~backend.graph.graphrag.GraphRAGResult` dict
        containing ``query``, ``mode``, ``vector_results``, ``graph_context``,
        ``matched_entities``, ``related_entities``, ``communities``,
        ``source_documents``, and ``combined_context``.
    """
    from backend.graph.graphrag import GraphRAGEngine  # noqa: PLC0415

    store = _get_store()
    user_roles = iam.get_user_roles(user_id)

    engine = GraphRAGEngine(graph_store=store, iam_engine=iam)

    result = await engine.search(
        query=body.query,
        user_id=user_id,
        user_roles=user_roles,
        mode=body.mode,
        n_results=body.n_results,
    )

    return {
        "query": result.query,
        "mode": result.mode,
        "vector_results": result.vector_results,
        "graph_context": result.graph_context,
        "matched_entities": result.matched_entities,
        "related_entities": result.related_entities,
        "communities": result.communities,
        "source_documents": result.source_documents,
        "combined_context": result.combined_context,
    }
