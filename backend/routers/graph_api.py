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
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.iam import IAMEngine
from backend.dependencies import get_current_user, get_iam, require_admin
from backend.agents.checkpointer import write_audit_record

logger = logging.getLogger(__name__)

router = APIRouter()


def _log_graph_action(user_id: str, action: str, detail: Any = None) -> None:
    """그래프 조작/조회에 대한 감사로그 기록."""
    try:
        write_audit_record({
            "thread_id": f"graph_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "user_id": user_id,
            "step": 0,
            "skill_name": f"graph.{action}",
            "input_payload": detail,
            "output_payload": None,
            "status": "success",
            "reasoning": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        logger.warning("Failed to write graph audit log", exc_info=True)

# ---------------------------------------------------------------------------
# Lazy singletons — imported on first request to avoid startup overhead
# ---------------------------------------------------------------------------

_graph_extractor: Any = None


def _get_layered() -> Any:
    from backend.graph.layered_store import get_layered_store
    return get_layered_store()


def _get_store(user_id: str | None = None) -> Any:
    """사용자 ID가 있으면 베이스+개인 병합 그래프, 없으면 베이스만."""
    layered = _get_layered()
    if user_id:
        return layered.merged_store(user_id)
    return layered.base


def _get_store_for_write(rel_path: str, user_id: str) -> Any:
    """문서 경로에 따라 쓸 그래프 반환 (Private→개인, 그 외→베이스)."""
    layered = _get_layered()
    return layered.get_store_for_path(rel_path, user_id)


def _get_extractor(store: Any = None) -> Any:
    """GraphExtractor를 반환. store를 지정하면 해당 store 사용."""
    global _graph_extractor
    if store:
        from backend.graph.extractor import GraphExtractor
        return GraphExtractor(graph_store=store)
    if _graph_extractor is None:
        from backend.graph.extractor import GraphExtractor
        _graph_extractor = GraphExtractor(graph_store=_get_layered().base)
    return _graph_extractor


_require_admin = require_admin  # backward compat alias


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


def _filter_entity_by_department(entity: Any, user_id: str, iam: IAMEngine) -> bool:
    """엔티티의 source_paths 중 하나라도 읽기 가능하면 True. source_paths 없으면 True."""
    source_paths = getattr(entity, "source_paths", [])
    if not source_paths:
        return True
    return any(iam.can_read(user_id, p) for p in source_paths)


@router.get("/entities", summary="엔티티 검색")
async def search_entities(
    q: str = Query("", description="검색 쿼리"),
    type: str | None = Query(None, description="엔티티 타입 필터"),
    limit: int = Query(20, ge=1, le=100, description="최대 결과 수"),
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """Search entities by fuzzy name matching, filtered by department ACL."""
    store = _get_store(user_id)
    # Over-fetch to compensate for ACL filtering
    results = store.search_entities(query=q, entity_type=type, limit=limit * 3)
    filtered = [e for e in results if _filter_entity_by_department(e, user_id, iam)][:limit]
    return {
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "entity_type": e.entity_type,
                "mentions": e.mentions,
                "source_paths": [p for p in e.source_paths if iam.can_read(user_id, p)],
                "properties": e.properties,
            }
            for e in filtered
        ],
        "total": len(filtered),
    }


@router.get("/entity/{entity_id}", summary="엔티티 상세 + 이웃")
async def get_entity(
    entity_id: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """Return entity details plus its immediate neighbours, filtered by department ACL."""
    store = _get_store(user_id)
    entity = store.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    # 부서 폴더 접근 제어: 엔티티 출처가 모두 접근 불가하면 404
    if not _filter_entity_by_department(entity, user_id, iam):
        raise HTTPException(status_code=403, detail="이 엔티티에 대한 접근 권한이 없습니다")

    _log_graph_action(user_id, "view_entity", {"entity_id": entity_id, "entity_name": entity.name})

    neighbors, relationships = store.get_neighbors(entity_id, depth=1)
    filtered_neighbors = [e for e in neighbors if _filter_entity_by_department(e, user_id, iam)]

    return {
        "entity": {
            "id": entity.id,
            "name": entity.name,
            "entity_type": entity.entity_type,
            "mentions": entity.mentions,
            "source_paths": [p for p in entity.source_paths if iam.can_read(user_id, p)],
            "properties": entity.properties,
        },
        "neighbors": [
            {
                "id": e.id,
                "name": e.name,
                "entity_type": e.entity_type,
                "mentions": e.mentions,
                "properties": e.properties or {},
                "source_paths": [p for p in (e.source_paths or []) if iam.can_read(user_id, p)],
            }
            for e in filtered_neighbors
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
            if not r.source_path or iam.can_read(user_id, r.source_path)
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
    store = _get_store(user_id)
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
    store = _get_store(user_id)
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
    store = _get_store(user_id)
    stats = store.get_stats()
    layered = _get_layered()
    stats["layers"] = layered.get_layer_stats(user_id)
    return stats


@router.get("/visualization", summary="전체 그래프 시각화 데이터")
async def get_visualization(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """Return the full graph filtered by department ACL."""
    store = _get_store(user_id)
    data = store.to_visualization_data()

    # 부서 ACL로 노드/엣지 필터링
    filtered_nodes = []
    accessible_ids: set[str] = set()
    for node in data.get("nodes", []):
        source_paths = node.get("source_paths", [])
        if not source_paths or any(iam.can_read(user_id, p) for p in source_paths):
            filtered_nodes.append(node)
            accessible_ids.add(node.get("id", ""))

    filtered_edges = [
        edge for edge in data.get("edges", [])
        if edge.get("source") in accessible_ids and edge.get("target") in accessible_ids
    ]

    return {
        "nodes": filtered_nodes,
        "edges": filtered_edges,
        "communities": data.get("communities", []),
    }


_graph_build_progress: dict[str, Any] = {
    "status": "idle",
    "total_files": 0,
    "processed": 0,
    "entities": 0,
    "relationships": 0,
    "errors": 0,
    "current_file": "",
}


@router.post("/build", summary="그래프 재구축 (관리자 전용)")
async def build_graph(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """비동기로 그래프를 재구축합니다. 진행 상황은 GET /build/progress로 조회."""
    _require_admin(user_id, iam)

    if _graph_build_progress["status"] == "running":
        return {"status": "already_running", "progress": _graph_build_progress}

    import asyncio
    from backend.config import settings as _settings

    async def _build_task():
        _graph_build_progress.update({
            "status": "running", "total_files": 0, "processed": 0,
            "entities": 0, "relationships": 0, "errors": 0, "current_file": "",
        })
        try:
            layered = _get_layered()
            extractor = _get_extractor(layered.base)

            # 파일 목록 수집
            vault_root = _settings.vault_root
            md_files = [
                f for f in vault_root.rglob("*.md")
                if f.is_file() and not f.name.startswith(".")
            ]
            # 이미 처리된 파일 목록 수집 (이어서 빌드)
            existing_paths: set[str] = set()
            try:
                for node_id in extractor._store._graph.nodes:
                    for sp in extractor._store._graph.nodes[node_id].get("source_paths", []):
                        existing_paths.add(sp)
            except Exception:
                pass

            remaining = [f for f in md_files if "/" + f.relative_to(vault_root).as_posix() not in existing_paths]
            _graph_build_progress["total_files"] = len(md_files)
            _graph_build_progress["processed"] = len(md_files) - len(remaining)
            _graph_build_progress["entities"] = extractor._store.get_stats().get("node_count", 0)
            _graph_build_progress["relationships"] = extractor._store.get_stats().get("edge_count", 0)

            logger.info("Graph build: %d total, %d already done, %d remaining", len(md_files), len(md_files) - len(remaining), len(remaining))

            # 파일별 추출 (진행률 추적)
            sem = asyncio.Semaphore(4)
            base_processed = len(md_files) - len(remaining)
            for i, md_file in enumerate(remaining):
                rel_path = "/" + md_file.relative_to(vault_root).as_posix()
                _graph_build_progress["current_file"] = md_file.name
                _graph_build_progress["processed"] = base_processed + i

                async with sem:
                    try:
                        ents, rels = await extractor.extract_from_file(md_file, rel_path)
                        _graph_build_progress["entities"] += len(ents)
                        _graph_build_progress["relationships"] += len(rels)
                    except Exception:
                        _graph_build_progress["errors"] += 1

            _graph_build_progress["processed"] = len(md_files)
            extractor._store.save()

            _graph_build_progress["status"] = "completed"
            _graph_build_progress["current_file"] = ""
            _log_graph_action(user_id, "build_full", dict(_graph_build_progress))

        except Exception as exc:
            logger.error("Graph build failed: %s", exc)
            _graph_build_progress["status"] = "error"
            _graph_build_progress["current_file"] = str(exc)

    asyncio.create_task(_build_task())
    return {"status": "started", "total_files": 0}


@router.get("/build/progress", summary="그래프 빌드 진행 상황")
async def build_progress(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """현재 그래프 빌드 진행 상황을 반환합니다."""
    return _graph_build_progress


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

    # 경로에 따라 적절한 레이어에 저장
    target_store = _get_store_for_write(body.rel_path, user_id)
    extractor = _get_extractor(target_store)
    entities, relationships = await extractor.extract_from_file(abs_path, body.rel_path)

    # 해당 레이어 저장
    target_store.save()
    layer = "personal" if body.rel_path.strip("/").startswith("Private/") else "base"

    _log_graph_action(user_id, "build_document", {
        "source_path": body.rel_path,
        "entities": len(entities),
        "relationships": len(relationships),
    })

    return {
        "status": "ok",
        "source_path": body.rel_path,
        "layer": layer,
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

    store = _get_store(user_id)
    user_roles = iam.get_user_roles(user_id)

    engine = GraphRAGEngine(graph_store=store, iam_engine=iam)

    result = await engine.search(
        query=body.query,
        user_id=user_id,
        user_roles=user_roles,
        mode=body.mode,
        n_results=body.n_results,
    )

    _log_graph_action(user_id, "search", {
        "query": body.query,
        "mode": body.mode,
        "matched_entities": len(result.matched_entities),
        "source_documents": result.source_documents,
    })

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
