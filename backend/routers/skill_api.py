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
        "display_name": "멀티소스 RAG 검색",
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
        "display_name": "지식그래프 검색",
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
        "display_name": "문서 검색",
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
        "display_name": "문서 읽기",
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
        "display_name": "웹 검색",
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
        "display_name": "보험료 계산기",
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
        "display_name": "문서 요약",
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
    {
        "skill_name": "underwriting",
        "display_name": "언더라이팅 사전심사",
        "description": "언더라이팅 사전심사 — 고객번호로 질병이력·직업·나이·성별·기가입/타사가입 내역을 자동 수집하고, 룰 기반 인수 심사 의견을 생성합니다.",
        "endpoint": "http://localhost:9001/api/v1/legacy/underwriting",
        "method": "POST",
        "category": "analysis",
        "params": {
            "customer_id": {"type": "string", "description": "고객 번호", "required": True},
            "product_code": {"type": "string", "description": "가입 신청 상품 코드", "required": True},
            "sum_insured": {"type": "number", "description": "가입금액 (원)", "required": False},
        },
        "inputs": {
            "customer_id": {"type": "string", "description": "고객 번호"},
            "product_code": {"type": "string", "description": "상품 코드"},
            "sum_insured": {"type": "number", "description": "가입금액"},
        },
        "outputs": {
            "assessment": {"type": "object", "description": "심사 결과 (decision, risk_factors, warnings)"},
            "collected_data": {"type": "object", "description": "수집된 원천 데이터 (질병이력, 직업, 가입내역)"},
        },
        "body": (
            "# 언더라이팅 사전심사\n\n"
            "고객번호 하나로 레거시 시스템에서 다음을 자동 수집합니다:\n\n"
            "- **고객 기본정보**: 나이, 성별\n"
            "- **질병이력**: 질병코드, 진단일, 상태(치료중/만성/완치), 중증도\n"
            "- **직업 정보**: 직업코드, 위험등급(1~5급)\n"
            "- **자사 기가입 내역**: 계약번호, 상품명, 가입금액, 상태\n"
            "- **타사 가입 내역**: 보험사명, 상품명, 가입금액, 상태\n\n"
            "수집된 데이터를 바탕으로 룰 기반 사전심사를 수행합니다:\n\n"
            "| 심사 결과 | 의미 |\n"
            "|-----------|------|\n"
            "| standard | 표준체 인수 |\n"
            "| substandard | 조건부 인수 (할증/부담보) |\n"
            "| decline | 인수 거절 |\n"
            "| refer | 전문 심사 회부 |\n"
        ),
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


class CodeSkillCreate(BaseModel):
    skill_name: str = Field(..., min_length=1)
    display_name: str = Field(...)
    description: str = Field(...)
    code: str = Field(...)
    params: dict[str, Any] = Field(default_factory=dict)
    category: str = Field(default="custom")


CODE_SKILLS_DIR = SKILLS_DIR / "custom"

# 코드 스킬에서 차단할 위험 패턴
_BLOCKED_CODE_PATTERNS = [
    "subprocess", "shutil", "__import__", "open(",
    "socket", "requests", "urllib", "http.client",
]


@router.post("/code/create")
async def create_code_skill(
    body: CodeSkillCreate,
    user_id: str = Depends(get_current_user),
):
    """Python 코드 기반 스킬을 생성합니다."""
    CODE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    path = CODE_SKILLS_DIR / f"{body.skill_name}.py"
    if path.exists():
        raise HTTPException(409, f"Code skill '{body.skill_name}' already exists")

    for pat in _BLOCKED_CODE_PATTERNS:
        if pat in body.code:
            raise HTTPException(400, f"보안 위반: '{pat}'은 코드 스킬에서 사용할 수 없습니다.")

    from backend.agents.skill_parser import SkillRegistry
    try:
        registry = SkillRegistry()
        registry.create_code_skill(
            skill_name=body.skill_name,
            display_name=body.display_name,
            description=body.description,
            code=body.code,
            params_schema=body.params,
            category=body.category,
        )
    except Exception as e:
        raise HTTPException(500, f"코드 스킬 생성 실패: {e}")

    _reload_registry()
    return {"status": "created", "skill_name": body.skill_name, "type": "code"}


@router.get("/code/list")
async def list_code_skills(user_id: str = Depends(get_current_user)):
    """코드 스킬 목록 조회."""
    CODE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skills = []
    for py_file in sorted(CODE_SKILLS_DIR.glob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        meta: dict[str, str] = {}
        for line in source.splitlines():
            if not line.startswith("# "):
                break
            parts = line[2:].split(":", 1)
            if len(parts) == 2:
                meta[parts[0].strip()] = parts[1].strip()
        skills.append({
            "skill_name": meta.get("skill", py_file.stem),
            "display_name": meta.get("display_name", py_file.stem),
            "description": meta.get("description", ""),
            "category": meta.get("category", "custom"),
            "file": py_file.name,
            "type": "code",
        })
    return {"skills": skills, "total": len(skills)}


@router.delete("/code/delete/{skill_name}")
async def delete_code_skill(skill_name: str, user_id: str = Depends(get_current_user)):
    """코드 스킬 삭제."""
    path = CODE_SKILLS_DIR / f"{skill_name}.py"
    if not path.exists():
        raise HTTPException(404, f"Code skill '{skill_name}' not found")
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
