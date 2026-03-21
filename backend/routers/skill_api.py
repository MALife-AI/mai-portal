"""Skill Management API — CRUD + 마켓플레이스."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.dependencies import get_current_user
from backend.config import settings
from backend.core.frontmatter import parse_frontmatter, synthesize_frontmatter

logger = logging.getLogger(__name__)

router = APIRouter()

SKILLS_DIR = Path(settings.vault_root).parent / "data" / "skills"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Models ───────────────────────────────────────────────────────────────────

class SkillParam(BaseModel):
    type: str = "string"
    description: str = ""
    required: bool = False
    default: Any = None


class SkillCreate(BaseModel):
    skill_name: str = Field(..., min_length=1, description="고유 스킬 ID (slug)")
    description: str = Field(..., description="스킬 설명 (LLM이 호출 판단에 사용)")
    endpoint: str = Field(..., description="호출할 API 엔드포인트")
    method: str = Field("POST", description="HTTP 메서드")
    params: dict[str, SkillParam] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    body: str = Field("", description="스킬 본문 설명 (마크다운)")
    category: str = Field("custom", description="카테고리: custom, search, analysis, report")


class SkillUpdate(BaseModel):
    description: str | None = None
    endpoint: str | None = None
    method: str | None = None
    params: dict[str, SkillParam] | None = None
    depends_on: list[str] | None = None
    body: str | None = None
    category: str | None = None


# ─── Marketplace 템플릿 ──────────────────────────────────────────────────────

MARKETPLACE_SKILLS: list[dict[str, Any]] = [
    {
        "skill_name": "multi-source-rag",
        "description": "멀티소스 RAG 검색 — 여러 문서에서 관련 내용을 검색하고 번호 매긴 출처를 반환합니다. 에이전트가 [1], [2] 형태로 인라인 인용할 수 있습니다.",
        "endpoint": "http://localhost:9001/api/v1/search/multi-source",
        "method": "POST",
        "category": "search",
        "params": {
            "query": {"type": "string", "description": "검색 쿼리", "required": True},
            "n_results": {"type": "integer", "description": "최대 결과 수", "required": False, "default": 5},
        },
        "body": "GraphRAG + 벡터 검색을 결합하여 여러 출처에서 관련 내용을 검색하고, 번호 매긴 출처 컨텍스트를 반환합니다.",
        "installed": False,
    },
    {
        "skill_name": "graphrag-search",
        "description": "지식그래프 기반 시맨틱 검색 — 질문과 관련된 보험 문서/엔티티를 검색합니다.",
        "endpoint": "http://localhost:9001/api/v1/graph/search",
        "method": "POST",
        "category": "search",
        "params": {
            "query": {"type": "string", "description": "검색 쿼리", "required": True},
            "mode": {"type": "string", "description": "검색 모드: local|global|hybrid", "required": False, "default": "hybrid"},
            "n_results": {"type": "integer", "description": "결과 수", "required": False, "default": 5},
        },
        "body": "GraphRAG 엔진을 사용하여 지식그래프에서 관련 엔티티와 문서를 검색합니다.",
        "installed": False,
    },
    {
        "skill_name": "vault-search",
        "description": "벡터 DB 시맨틱 검색 — ChromaDB에서 유사 문서 청크를 검색합니다.",
        "endpoint": "http://localhost:9001/api/v1/search/",
        "method": "GET",
        "category": "search",
        "params": {
            "q": {"type": "string", "description": "검색 쿼리", "required": True},
            "n": {"type": "integer", "description": "결과 수", "required": False, "default": 10},
        },
        "body": "ChromaDB 벡터 검색으로 vault 내 관련 문서 청크를 찾습니다.",
        "installed": False,
    },
    {
        "skill_name": "vault-read",
        "description": "vault 문서 읽기 — 경로를 지정하여 마크다운 문서 내용을 조회합니다.",
        "endpoint": "http://localhost:9001/api/v1/vault/read",
        "method": "GET",
        "category": "search",
        "params": {
            "path": {"type": "string", "description": "문서 상대 경로", "required": True},
        },
        "body": "vault 내 특정 문서의 전체 내용을 조회합니다.",
        "installed": False,
    },
    {
        "skill_name": "web-search",
        "description": "웹 검색 — 인터넷에서 최신 정보를 검색합니다.",
        "endpoint": "https://api.duckduckgo.com/",
        "method": "GET",
        "category": "search",
        "params": {
            "q": {"type": "string", "description": "검색 쿼리", "required": True},
            "format": {"type": "string", "description": "응답 형식", "required": False, "default": "json"},
        },
        "body": "DuckDuckGo API를 사용한 웹 검색.",
        "installed": False,
    },
    {
        "skill_name": "insurance-calculator",
        "description": "보험료 계산기 — 나이, 성별, 상품코드로 예상 보험료를 계산합니다.",
        "endpoint": "http://localhost:9001/api/v1/legacy/calculate",
        "method": "POST",
        "category": "analysis",
        "params": {
            "product_code": {"type": "string", "description": "상품 코드", "required": True},
            "age": {"type": "integer", "description": "나이", "required": True},
            "gender": {"type": "string", "description": "성별 (M/F)", "required": True},
        },
        "body": "레거시 시스템의 보험료 계산 API를 호출합니다.",
        "installed": False,
    },
    {
        "skill_name": "document-summary",
        "description": "문서 요약 — 지정된 문서를 읽고 핵심 내용을 요약합니다.",
        "endpoint": "http://localhost:9001/api/v1/agent/run",
        "method": "POST",
        "category": "analysis",
        "params": {
            "query": {"type": "string", "description": "요약할 문서 경로 또는 요약 요청", "required": True},
        },
        "body": "에이전트를 재귀적으로 호출하여 문서를 요약합니다.",
        "installed": False,
    },
]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_skills(user_id: str = Depends(get_current_user)):
    """설치된 스킬 목록 조회."""
    skills = []
    for md_file in sorted(SKILLS_DIR.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            if meta.get("type") != "skill":
                continue
            skills.append({
                **meta,
                "body": body.strip()[:500],
                "file": md_file.name,
            })
        except Exception as e:
            logger.warning("Failed to read skill %s: %s", md_file, e)
    return {"skills": skills, "total": len(skills)}


@router.get("/get/{skill_name}")
async def get_skill(skill_name: str, user_id: str = Depends(get_current_user)):
    """스킬 상세 조회."""
    path = SKILLS_DIR / f"{skill_name}.md"
    if not path.exists():
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    content = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)
    return {**meta, "body": body.strip()}


@router.post("/create")
async def create_skill(skill: SkillCreate, user_id: str = Depends(get_current_user)):
    """새 스킬 생성."""
    path = SKILLS_DIR / f"{skill.skill_name}.md"
    if path.exists():
        raise HTTPException(409, f"Skill '{skill.skill_name}' already exists")

    meta = {
        "type": "skill",
        "skill_name": skill.skill_name,
        "description": skill.description,
        "endpoint": skill.endpoint,
        "method": skill.method,
        "params": {k: v.model_dump() for k, v in skill.params.items()},
        "depends_on": skill.depends_on,
        "category": skill.category,
        "owner": user_id,
    }
    content = synthesize_frontmatter(skill.body or f"# {skill.skill_name}\n\n{skill.description}", user_id=user_id, extra_meta=meta)
    path.write_text(content, encoding="utf-8")

    # 스킬 레지스트리 리로드
    _reload_registry()

    return {"status": "created", "skill_name": skill.skill_name}


@router.put("/update/{skill_name}")
async def update_skill(skill_name: str, update: SkillUpdate, user_id: str = Depends(get_current_user)):
    """스킬 수정."""
    path = SKILLS_DIR / f"{skill_name}.md"
    if not path.exists():
        raise HTTPException(404, f"Skill '{skill_name}' not found")

    content = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)

    if update.description is not None:
        meta["description"] = update.description
    if update.endpoint is not None:
        meta["endpoint"] = update.endpoint
    if update.method is not None:
        meta["method"] = update.method
    if update.params is not None:
        meta["params"] = {k: v.model_dump() for k, v in update.params.items()}
    if update.depends_on is not None:
        meta["depends_on"] = update.depends_on
    if update.body is not None:
        body = update.body
    if update.category is not None:
        meta["category"] = update.category

    new_content = synthesize_frontmatter(body, user_id=user_id, extra_meta=meta)
    path.write_text(new_content, encoding="utf-8")
    _reload_registry()

    return {"status": "updated", "skill_name": skill_name}


@router.delete("/delete/{skill_name}")
async def delete_skill(skill_name: str, user_id: str = Depends(get_current_user)):
    """스킬 삭제."""
    path = SKILLS_DIR / f"{skill_name}.md"
    if not path.exists():
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    path.unlink()
    _reload_registry()
    return {"status": "deleted", "skill_name": skill_name}


@router.get("/marketplace")
async def marketplace(user_id: str = Depends(get_current_user)):
    """마켓플레이스 — 설치 가능한 스킬 템플릿 목록."""
    installed = {p.stem for p in SKILLS_DIR.glob("*.md")}
    items = []
    for tpl in MARKETPLACE_SKILLS:
        items.append({**tpl, "installed": tpl["skill_name"] in installed})
    return {"skills": items, "total": len(items)}


@router.post("/marketplace/install/{skill_name}")
async def install_from_marketplace(skill_name: str, user_id: str = Depends(get_current_user)):
    """마켓플레이스에서 스킬 설치."""
    tpl = next((s for s in MARKETPLACE_SKILLS if s["skill_name"] == skill_name), None)
    if not tpl:
        raise HTTPException(404, f"Marketplace skill '{skill_name}' not found")

    path = SKILLS_DIR / f"{skill_name}.md"
    if path.exists():
        raise HTTPException(409, f"Skill '{skill_name}' already installed")

    params = {}
    for k, v in tpl.get("params", {}).items():
        params[k] = v

    meta = {
        "type": "skill",
        "skill_name": skill_name,
        "description": tpl["description"],
        "endpoint": tpl["endpoint"],
        "method": tpl.get("method", "GET"),
        "params": params,
        "depends_on": tpl.get("depends_on", []),
        "category": tpl.get("category", "custom"),
        "owner": user_id,
    }
    body = tpl.get("body", f"# {skill_name}")
    content = synthesize_frontmatter(body, user_id=user_id, extra_meta=meta)
    path.write_text(content, encoding="utf-8")
    _reload_registry()

    return {"status": "installed", "skill_name": skill_name}


def _reload_registry():
    """에이전트의 스킬 레지스트리를 리로드."""
    try:
        from backend.routers.agent_api import _registry
        _registry.reload()
    except Exception:
        logger.debug("Skill registry reload failed (non-fatal)", exc_info=True)
