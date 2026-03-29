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

import asyncio
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
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
    from backend.config import settings
    _model = settings.graph_extract_model or None
    if store:
        from backend.graph.extractor import GraphExtractor
        return GraphExtractor(graph_store=store, model=_model)
    if _graph_extractor is None:
        from backend.graph.extractor import GraphExtractor
        _graph_extractor = GraphExtractor(graph_store=_get_layered().base, model=_model)
    return _graph_extractor


_require_admin = require_admin  # backward compat alias


# ---------------------------------------------------------------------------
# LLM 서버 모델 스왑 (그래프 추출 시 경량 모델 사용)
# ---------------------------------------------------------------------------

_LLAMA_SERVER_BIN = "/home/lsc/malife-gpu-server/llama-src/build/bin/llama-server"
_LLAMA_SERVER_TQ_BIN = "/home/lsc/malife-gpu-server/llama-turboquant/build/bin/llama-server"
_MODELS_DIR = Path("/home/lsc/malife-gpu-server/models")
_SERVER_LOG = "/home/lsc/malife-gpu-server/server.log"
_LLAMA_PORT = 8801

# 모델 프로파일: (파일명, alias, parallel, ctx-size, extra_args)
_MODEL_PROFILES = {
    "main": ("Qwen3.5-27B-Q4_K_M.gguf", "qwen3.5-27b", 2, 32768,
             ["--cache-type-k", "tq_pq3", "--cache-type-v", "f16"]),
    "extract": ("Qwen3.5-9B-UD-Q4_K_XL.gguf", "qwen3.5-9b", 4, 65536,
                ["--cache-type-k", "tq_pq3", "--cache-type-v", "f16"]),
}


async def _swap_llama_model(profile: str) -> None:
    """llama-server를 지정 프로파일로 재시작합니다."""
    model_file, alias, parallel, ctx_size, extra_args = _MODEL_PROFILES[profile]
    model_path = _MODELS_DIR / model_file

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    # TQ args가 있으면 TQ 바이너리 사용
    server_bin = _LLAMA_SERVER_TQ_BIN if extra_args else _LLAMA_SERVER_BIN

    # 기존 서버 종료
    subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
    await asyncio.sleep(2)

    # 새 서버 시작
    cmd = [
        server_bin,
        "--model", str(model_path),
        "--alias", alias,
        "--ctx-size", str(ctx_size),
        "--n-gpu-layers", "999",
        "--parallel", str(parallel),
        "--cont-batching",
        "--metrics",
        "--host", "0.0.0.0",
        "--port", str(_LLAMA_PORT),
        "--jinja",
    ] + extra_args
    with open(_SERVER_LOG, "w") as log_f:
        subprocess.Popen(cmd, stdout=log_f, stderr=log_f)

    # 서버 준비 대기 (최대 120초)
    async with httpx.AsyncClient() as client:
        for _ in range(60):
            await asyncio.sleep(2)
            try:
                r = await client.get(f"http://localhost:{_LLAMA_PORT}/health")
                if r.status_code == 200:
                    logger.info("llama-server swapped to profile=%s (%s)", profile, alias)
                    return
            except httpx.ConnectError:
                continue
    raise TimeoutError(f"llama-server failed to start with profile={profile}")


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


_graph_build_cancelled = False

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
        global _graph_build_cancelled
        _graph_build_cancelled = False
        _graph_build_progress.update({
            "status": "running", "total_files": 0, "processed": 0,
            "entities": 0, "relationships": 0, "errors": 0, "current_file": "초기화 중...",
        })
        _swapped = False
        try:
            # ── 추출 전용 모델로 교체 ──
            extract_model = _settings.graph_extract_model
            if extract_model and (_MODELS_DIR / _MODEL_PROFILES.get("extract", ("",))[0]).exists():
                _graph_build_progress["current_file"] = "모델 교체 중 (9B)..."
                await _swap_llama_model("extract")
                _swapped = True

            # 빌드마다 store를 디스크에서 새로 로드 (중간저장 결과 반영)
            from backend.graph.layered_store import get_layered_store
            layered = get_layered_store(force_reload=True)
            from backend.graph.extractor import GraphExtractor
            _model = _settings.graph_extract_model or None
            extractor = GraphExtractor(graph_store=layered.base, model=_model)
            # 모델 교체 시 LLM 인스턴스 리셋
            if _swapped:
                extractor._llm = None
                extractor._model = extract_model

            # 파일 목록 수집
            vault_root = _settings.vault_root
            md_files = [
                f for f in vault_root.rglob("*.md")
                if f.is_file() and not f.name.startswith(".")
            ]
            # 이미 처리된 파일 목록 수집 (이어서 빌드 — 파일명 NFC 정규화 매칭)
            import unicodedata as _ud
            existing_filenames: set[str] = set()
            try:
                for node_id in extractor._store._graph.nodes:
                    for sp in extractor._store._graph.nodes[node_id].get("source_paths", []):
                        existing_filenames.add(_ud.normalize("NFC", sp.rsplit("/", 1)[-1]))
            except Exception:
                pass

            remaining = [f for f in md_files if _ud.normalize("NFC", f.name) not in existing_filenames]
            _graph_build_progress["total_files"] = len(md_files)
            _graph_build_progress["processed"] = len(md_files) - len(remaining)
            _graph_build_progress["entities"] = extractor._store.get_stats().get("node_count", 0)
            _graph_build_progress["relationships"] = extractor._store.get_stats().get("edge_count", 0)

            logger.info("Graph build: %d total, %d already done, %d remaining", len(md_files), len(md_files) - len(remaining), len(remaining))

            # 파일별 추출 (병렬 + 실시간 진행률)
            _parallel = _MODEL_PROFILES["extract"][2] if _swapped else 4
            sem = asyncio.Semaphore(_parallel)
            base_processed = len(md_files) - len(remaining)
            _completed_count = 0

            _CHECKPOINT_INTERVAL = 20  # 20파일마다 중간 저장

            _TIMEOUT_BASE = 600   # 기준 timeout 10분 (8KB 약관 기준)
            _TIMEOUT_BASE_KB = 8  # 기준 파일 크기 8KB
            _TIMEOUT_RETRY_MULT = 2  # 재시도 시 2배
            _failed_files: list[Path] = []

            def _calc_timeout(md_file: Path, multiplier: int = 1) -> int:
                size_kb = max(md_file.stat().st_size / 1024, _TIMEOUT_BASE_KB)
                return int(_TIMEOUT_BASE * (size_kb / _TIMEOUT_BASE_KB) * multiplier)

            async def _extract_file(ext, md_file, rel_path):
                ents, rels = await ext.extract_from_file(md_file, rel_path)
                _graph_build_progress["entities"] += len(ents)
                _graph_build_progress["relationships"] += len(rels)

            async def _process_one(md_file: Path, timeout_mult: int = 1):
                nonlocal _completed_count
                if _graph_build_cancelled:
                    return
                rel_path = "/" + md_file.relative_to(vault_root).as_posix()
                timeout = _calc_timeout(md_file, timeout_mult)
                async with sem:
                    if _graph_build_cancelled:
                        return
                    _graph_build_progress["current_file"] = md_file.name
                    try:
                        await asyncio.wait_for(
                            _extract_file(extractor, md_file, rel_path),
                            timeout=timeout,
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Timeout extracting %s (timeout=%ds)", md_file.name, timeout)
                        _failed_files.append(md_file)
                    except Exception as exc:
                        logger.warning("Error extracting %s: %s", md_file.name, exc)
                        _failed_files.append(md_file)
                    finally:
                        _completed_count += 1
                        _graph_build_progress["processed"] = base_processed + _completed_count
                        if _completed_count % _CHECKPOINT_INTERVAL == 0:
                            try:
                                extractor._store.save()
                                logger.info("Graph checkpoint saved at %d files", _completed_count)
                            except Exception:
                                pass

            # 1차 처리
            await asyncio.gather(*[_process_one(f) for f in remaining], return_exceptions=True)
            extractor._store.save()
            logger.info("Graph saved after 1st pass (%d files)", _completed_count)

            if _graph_build_cancelled:
                _graph_build_progress["status"] = "cancelled"
                _graph_build_progress["current_file"] = ""
                return

            # 재시도: 파일 크기 비례 timeout × 2배 / 4배
            _retry_queue = list(_failed_files)
            for attempt, mult in [(1, _TIMEOUT_RETRY_MULT), (2, _TIMEOUT_RETRY_MULT * 2)]:
                if not _retry_queue or _graph_build_cancelled:
                    break
                logger.info("Retry round %d: %d files, timeout_mult=%dx", attempt, len(_retry_queue), mult)
                _graph_build_progress["retry_round"] = attempt
                _graph_build_progress["retry_total"] = len(_retry_queue)
                _graph_build_progress["retry_done"] = 0
                _graph_build_progress["retry_failed"] = 0
                next_failed: list[Path] = []
                retry_count = 0
                for md_file in _retry_queue:
                    if _graph_build_cancelled:
                        break
                    timeout = _calc_timeout(md_file, mult)
                    rel_path = "/" + md_file.relative_to(vault_root).as_posix()
                    _graph_build_progress["current_file"] = f"재시도{attempt}차: {md_file.name} ({timeout}s)"
                    try:
                        await asyncio.wait_for(
                            _extract_file(extractor, md_file, rel_path),
                            timeout=timeout,
                        )
                        _graph_build_progress["errors"] = max(0, _graph_build_progress["errors"] - 1)
                    except Exception as exc:
                        logger.warning("Retry%d failed for %s: %s", attempt, md_file.name, exc)
                        next_failed.append(md_file)
                        _graph_build_progress["retry_failed"] += 1
                    finally:
                        retry_count += 1
                        _graph_build_progress["retry_done"] = retry_count
                        if retry_count % 10 == 0:
                            extractor._store.save()
                            logger.info("Graph checkpoint saved during retry%d (%d/%d)", attempt, retry_count, len(_retry_queue))
                extractor._store.save()
                _retry_queue = next_failed
            if _retry_queue:
                logger.warning("Permanently failed files (%d): %s", len(_retry_queue), [f.name for f in _retry_queue])
            # 재시도 필드 정리
            for k in ("retry_round", "retry_total", "retry_done", "retry_failed"):
                _graph_build_progress.pop(k, None)
            _graph_build_progress["processed"] = len(md_files)

            # ── 이미지 엔티티 추출 (vault/assets/) ──────────────────
            assets_dir = vault_root / "assets"
            if assets_dir.exists():
                image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
                image_files = [
                    f for f in assets_dir.rglob("*")
                    if f.is_file() and f.suffix.lower() in image_exts
                ]
                if image_files:
                    _graph_build_progress["current_file"] = f"이미지 처리 ({len(image_files)}건)"
                    logger.info("Graph build: processing %d images from assets/", len(image_files))
                    try:
                        from backend.ingestion.vlm_processor import get_image_processor
                        from backend.graph.models import Entity, Relationship

                        processor = get_image_processor()
                        img_sem = asyncio.Semaphore(2)

                        async def _process_image(img_path: Path):
                            async with img_sem:
                                try:
                                    result = await processor.analyze_image(img_path)
                                    caption = result.get("caption", "") or img_path.stem
                                    img_type = result.get("type", "diagram")
                                    table_md = result.get("markdown_table", "")
                                    rel_path = "/" + img_path.relative_to(vault_root).as_posix()
                                    parent_doc = img_path.parent.name
                                    source = [f"/assets/{parent_doc}/{img_path.name}"]

                                    if img_type == "table" and table_md:
                                        entity = Entity(
                                            id=f"tbl_{img_path.stem}",
                                            name=f"표: {parent_doc}" if parent_doc else f"표: {img_path.stem}",
                                            entity_type="table",
                                            properties={
                                                "image_path": rel_path,
                                                "raw_markdown": table_md[:800],
                                                "parent_document": parent_doc,
                                            },
                                            source_paths=source,
                                            mentions=1,
                                        )
                                        extractor._store.add_entity(entity)
                                        _graph_build_progress["entities"] += 1

                                        # 표 팩트 분해
                                        try:
                                            facts = await extractor._decompose_table(table_md, parent_doc)
                                            for fact in facts:
                                                fact_ent = Entity(
                                                    id=f"fact_{img_path.stem}_{fact['key'][:30].replace(' ', '_')}",
                                                    name=fact["key"],
                                                    entity_type="fact",
                                                    properties={
                                                        "value": fact["value"],
                                                        "context": fact.get("context", ""),
                                                        "parent_table": f"tbl_{img_path.stem}",
                                                        "parent_document": parent_doc,
                                                    },
                                                    source_paths=source,
                                                    mentions=1,
                                                )
                                                extractor._store.add_entity(fact_ent)
                                                extractor._store.add_relationship(Relationship(
                                                    source_id=f"tbl_{img_path.stem}",
                                                    target_id=fact_ent.id,
                                                    relation_type="contains",
                                                    source_path=rel_path,
                                                ))
                                                _graph_build_progress["entities"] += 1
                                                _graph_build_progress["relationships"] += 1
                                        except Exception:
                                            pass
                                    else:
                                        entity = Entity(
                                            id=f"img_{img_path.stem}",
                                            name=caption[:80] if caption else img_path.stem,
                                            entity_type="image",
                                            properties={
                                                "image_path": rel_path,
                                                "caption": caption[:200],
                                                "parent_document": parent_doc,
                                            },
                                            source_paths=source,
                                            mentions=1,
                                        )
                                        extractor._store.add_entity(entity)
                                        _graph_build_progress["entities"] += 1
                                except Exception:
                                    _graph_build_progress["errors"] += 1

                        await asyncio.gather(*[_process_image(f) for f in image_files[:100]])
                    except Exception as exc:
                        logger.warning("Image entity extraction failed: %s", exc)

            extractor._store.save()

            _graph_build_progress["status"] = "completed"
            _graph_build_progress["current_file"] = ""
            _log_graph_action(user_id, "build_full", dict(_graph_build_progress))

        except Exception as exc:
            logger.error("Graph build failed: %s", exc)
            _graph_build_progress["status"] = "error"
            _graph_build_progress["current_file"] = str(exc)
        finally:
            # ── 메인 모델로 복원 ──
            if _swapped:
                try:
                    _graph_build_progress["current_file"] = "모델 복원 중 (27B)..."
                    await _swap_llama_model("main")
                    # extractor LLM 리셋
                    extractor._llm = None
                    extractor._model = _settings.vlm_model
                except Exception as swap_err:
                    logger.error("Failed to restore main model: %s", swap_err)

    asyncio.create_task(_build_task())
    return {"status": "started", "total_files": 0}


@router.post("/fix-paths", summary="그래프 source_paths 일괄 수정")
async def fix_source_paths(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, Any]:
    """그래프 노드의 source_paths를 실제 vault 경로와 매칭하여 수정합니다."""
    _require_admin(user_id, iam)

    from backend.config import settings as _s
    import asyncio

    def _fix():
        store = _get_store()
        vault_root = _s.vault_root

        # vault 내 실제 파일 경로 인덱스 (파일명 → 전체 상대 경로)
        file_index: dict[str, str] = {}
        for md_file in vault_root.rglob("*.md"):
            rel = md_file.relative_to(vault_root).as_posix()
            file_index[md_file.name] = rel

        fixed_count = 0
        for node_id in store._graph.nodes:
            data = store._graph.nodes[node_id]
            paths = data.get("source_paths", [])
            if not paths:
                continue

            new_paths = []
            changed = False
            for p in paths:
                # 파일명 추출
                fname = p.split("/")[-1].split("@")[0]
                if fname in file_index:
                    correct = file_index[fname]
                    if correct != p and correct != p.lstrip("/"):
                        new_paths.append(correct)
                        changed = True
                        continue
                # 선행 슬래시 + Public → Shared 치환
                normalized = p.lstrip("/").replace("Public/", "Shared/", 1)
                if normalized != p:
                    new_paths.append(normalized)
                    changed = True
                else:
                    new_paths.append(p)

            if changed:
                data["source_paths"] = new_paths
                fixed_count += 1

        store.save()
        return fixed_count

    count = await asyncio.to_thread(_fix)
    return {"status": "fixed", "nodes_updated": count}


@router.get("/build/progress", summary="그래프 빌드 진행 상황")
async def build_progress(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """현재 그래프 빌드 진행 상황을 반환합니다."""
    return _graph_build_progress


@router.post("/build/cancel", summary="그래프 빌드 취소 (관리자 전용)")
async def cancel_build(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, str]:
    """진행 중인 빌드를 취소합니다. 중간 결과는 저장됩니다."""
    _require_admin(user_id, iam)
    global _graph_build_cancelled
    if _graph_build_progress["status"] != "running":
        return {"status": "not_running"}
    _graph_build_cancelled = True
    return {"status": "cancelling"}


@router.post("/build/reset", summary="그래프 빌드 상태 리셋 (관리자 전용)")
async def reset_build_progress(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
) -> dict[str, str]:
    """멈춘 빌드 상태를 idle로 리셋합니다."""
    _require_admin(user_id, iam)
    global _graph_build_cancelled
    _graph_build_cancelled = True
    _graph_build_progress.update({
        "status": "idle", "total_files": 0, "processed": 0,
        "entities": 0, "relationships": 0, "errors": 0, "current_file": "",
    })
    return {"status": "reset"}


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
