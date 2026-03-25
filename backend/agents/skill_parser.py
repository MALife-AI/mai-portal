"""Skill Parser: type:skill 마크다운 → LangChain Tool 동적 변환."""
from __future__ import annotations

import logging
import sys
from collections import deque
from pathlib import Path
from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from backend.core.frontmatter import parse_frontmatter
from backend.config import settings

logger = logging.getLogger(__name__)

# Pydantic 필드 타입 매핑: frontmatter 타입 문자열 → Python 타입
_PARAM_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class CircularDependencyError(Exception):
    """스킬 의존성 그래프에 순환 참조가 있을 때 발생."""


class SkillRegistry:
    """Vault 내 type:skill 마크다운을 스캔하여 Tool 객체로 관리."""

    def __init__(self, skills_dir: Path | None = None) -> None:
        self._skills_dir = skills_dir or Path(settings.vault_root).parent / "data" / "skills"
        self._skills: dict[str, dict[str, Any]] = {}
        self._tools: dict[str, StructuredTool] = {}

    # ------------------------------------------------------------------
    # Public: 로드 / 리로드
    # ------------------------------------------------------------------

    def load_all(self) -> None:
        """data/skills/ 디렉토리를 스캔하여 모든 스킬을 로드."""
        # 1) 파일 기반 스킬 로드
        skills_dir = self._skills_dir
        if skills_dir.exists():
            for md_file in skills_dir.glob("**/*.md"):
                try:
                    self._load_skill(md_file)
                except Exception as e:
                    logger.error("Failed to load skill %s: %s", md_file, e)

        # 2) 코드 스킬 로드 (data/skills/custom/*.py)
        try:
            self._load_code_skills()
        except Exception as e:
            logger.error("Failed to load code skills: %s", e)

        # 3) 내장 프롬프트 스킬 등록 (파일 스킬보다 우선 — 동일 이름 덮어씀)
        try:
            self.register_graphrag_skills()
        except Exception as e:
            logger.error("Failed to register GraphRAG skills: %s", e)

    def reload(self) -> None:
        """Skills/ 디렉토리를 재스캔하여 레지스트리를 갱신한다.

        기존에 로드된 스킬과 툴을 모두 지우고 처음부터 다시 로드한다.
        실행 중인 에이전트에 이미 전달된 Tool 참조는 갱신되지 않으므로
        에이전트 재초기화 시점에 맞춰 호출할 것.
        """
        self._skills.clear()
        self._tools.clear()
        self.load_all()
        logger.info("SkillRegistry reloaded — %d skills registered", len(self._skills))

    # ------------------------------------------------------------------
    # Public: 조회
    # ------------------------------------------------------------------

    def list_skills(self) -> list[dict[str, Any]]:
        """로드된 전체 스킬 메타데이터 목록을 반환."""
        return list(self._skills.values())

    def get_skill(self, name: str) -> dict[str, Any] | None:
        """이름으로 스킬 메타데이터를 반환."""
        return self._skills.get(name)

    def get_tool(self, name: str) -> StructuredTool | None:
        """이름으로 LangChain StructuredTool 인스턴스를 반환."""
        return self._tools.get(name)

    # ------------------------------------------------------------------
    # Public: 의존성 분석
    # ------------------------------------------------------------------

    def topological_sort(self) -> list[str]:
        """Kahn's 알고리즘으로 스킬 의존성 그래프를 위상 정렬한다.

        Returns:
            실행 순서대로 정렬된 스킬 이름 목록 (선행 스킬이 먼저 위치).

        Raises:
            CircularDependencyError: 의존성 그래프에 사이클이 존재할 때.
        """
        # in-degree 초기화
        in_degree: dict[str, int] = {name: 0 for name in self._skills}
        adjacency: dict[str, list[str]] = {name: [] for name in self._skills}

        for name, meta in self._skills.items():
            for dep in meta.get("depends_on", []):
                if dep in self._skills:
                    adjacency[dep].append(name)
                    in_degree[name] += 1

        queue: deque[str] = deque(
            name for name, degree in in_degree.items() if degree == 0
        )
        sorted_skills: list[str] = []

        while queue:
            node = queue.popleft()
            sorted_skills.append(node)
            for successor in adjacency[node]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(sorted_skills) != len(self._skills):
            # 방문하지 못한 노드가 있다면 사이클 존재
            cycle_nodes = [n for n in self._skills if n not in sorted_skills]
            raise CircularDependencyError(
                f"Circular dependency detected among skills: {cycle_nodes}"
            )

        return sorted_skills

    def get_execution_plan(self, skill_name: str) -> list[dict[str, Any]]:
        """대상 스킬의 전이적 의존성을 포함한 실행 계획을 반환한다.

        BFS로 의존성 서브그래프를 수집한 뒤, 전체 위상 정렬 결과에서
        서브그래프에 속하는 노드만 순서대로 추출하여 반환한다.

        Args:
            skill_name: 최종적으로 실행할 스킬 이름.

        Returns:
            순서대로 실행해야 할 스킬 정보 딕셔너리 목록.
            각 항목은 ``{"step": int, "skill": str, "endpoint": str,
            "method": str, "depends_on": list[str]}`` 형식.

        Raises:
            KeyError: skill_name 이 레지스트리에 없을 때.
            CircularDependencyError: 의존성 그래프에 사이클이 있을 때.
        """
        if skill_name not in self._skills:
            raise KeyError(f"Skill '{skill_name}' not found in registry")

        # BFS 로 연관 스킬 집합 수집
        involved: set[str] = set()
        queue: deque[str] = deque([skill_name])
        while queue:
            current = queue.popleft()
            if current in involved:
                continue
            involved.add(current)
            for dep in self._skills.get(current, {}).get("depends_on", []):
                if dep not in involved:
                    queue.append(dep)

        # 전체 위상 정렬에서 서브그래프 순서만 추출
        full_order = self.topological_sort()
        ordered = [s for s in full_order if s in involved]

        return [
            {
                "step": idx + 1,
                "skill": name,
                "endpoint": self._skills[name]["endpoint"],
                "method": self._skills[name]["method"],
                "depends_on": self._skills[name]["depends_on"],
            }
            for idx, name in enumerate(ordered)
        ]

    # ------------------------------------------------------------------
    # Public: 검증
    # ------------------------------------------------------------------

    def validate_all(self) -> list[str]:
        """모든 스킬의 구성 무결성을 검사하고 경고 메시지 목록을 반환한다.

        검사 항목:
        - depends_on 에 기재된 스킬이 레지스트리에 존재하는지 여부
        - endpoint 미설정 여부
        - 순환 의존성 존재 여부
        - required 파라미터에 타입 정보가 있는지 여부

        Returns:
            발견된 경고/오류 메시지 목록. 비어 있으면 이상 없음.
        """
        warnings: list[str] = []
        known = set(self._skills)

        for name, meta in self._skills.items():
            # 1) endpoint 설정 여부
            if not meta.get("endpoint"):
                warnings.append(f"[{name}] endpoint is not configured")

            # 2) depends_on 참조 무결성
            for dep in meta.get("depends_on", []):
                if dep not in known:
                    warnings.append(
                        f"[{name}] depends_on '{dep}' is not in the registry"
                    )

            # 3) 파라미터 타입 명시 여부
            for param_name, param_meta in meta.get("params_schema", {}).items():
                if not isinstance(param_meta, dict):
                    warnings.append(
                        f"[{name}] param '{param_name}' has invalid schema (not a dict)"
                    )
                    continue
                if param_meta.get("required", False) and "type" not in param_meta:
                    warnings.append(
                        f"[{name}] required param '{param_name}' is missing 'type'"
                    )

        # 4) 순환 의존성
        try:
            self.topological_sort()
        except CircularDependencyError as exc:
            warnings.append(f"[CIRCULAR DEPENDENCY] {exc}")

        return warnings

    # ------------------------------------------------------------------
    # Private: 로드 / 빌드
    # ------------------------------------------------------------------

    def _load_skill(self, path: Path) -> None:
        content = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        if meta.get("type") != "skill":
            return

        name = meta.get("skill_name", path.stem)
        endpoint = meta.get("endpoint", "")
        depends_on = meta.get("depends_on", [])
        description = meta.get("description", body[:200])
        method = meta.get("method", "POST").upper()
        params_schema = meta.get("params", {})

        self._skills[name] = {
            "name": name,
            "endpoint": endpoint,
            "depends_on": depends_on,
            "description": description,
            "method": method,
            "params_schema": params_schema,
            "source": str(path),
        }

        # Pydantic 스키마 기반 LangChain Tool 동적 생성
        args_schema = self._build_pydantic_schema(params_schema)
        tool = self._create_tool(name, endpoint, method, description, args_schema)
        self._tools[name] = tool
        logger.info("Loaded skill: %s (depends_on: %s)", name, depends_on)

    def _build_pydantic_schema(self, params: dict[str, Any]) -> type[BaseModel]:
        """frontmatter params 딕셔너리로부터 Pydantic BaseModel 클래스를 동적 생성한다.

        Args:
            params: 스킬 frontmatter 의 ``params`` 섹션 딕셔너리.
                각 값은 ``{type, required, description, default}`` 구조.

        Returns:
            pydantic.create_model 로 생성된 BaseModel 서브클래스.
            파라미터가 없으면 빈 모델을 반환한다.
        """
        field_definitions: dict[str, Any] = {}

        for param_name, param_meta in params.items():
            if not isinstance(param_meta, dict):
                continue

            raw_type = param_meta.get("type", "string")
            python_type = _PARAM_TYPE_MAP.get(raw_type, str)
            is_required: bool = param_meta.get("required", True)
            description: str = param_meta.get("description", "")
            default = param_meta.get("default", ...)  # ... = PydanticRequired

            if not is_required and default is ...:
                # optional 이지만 default 미지정 → None 허용
                python_type = python_type | None  # type: ignore[assignment]
                default = None

            field_definitions[param_name] = (
                python_type,
                Field(default=default, description=description),
            )

        # 모델 이름이 고유해야 Pydantic 내부 캐시와 충돌하지 않는다
        return create_model("SkillParams", **field_definitions)  # type: ignore[call-overload]

    def _create_tool(
        self,
        name: str,
        endpoint: str,
        method: str,
        description: str,
        args_schema: type[BaseModel],
    ) -> StructuredTool:
        async def _invoke(**kwargs: Any) -> str:
            if not endpoint:
                return f"[Skill {name}] No endpoint configured"
            async with httpx.AsyncClient(timeout=30) as client:
                if method == "GET":
                    resp = await client.get(endpoint, params=kwargs)
                else:
                    resp = await client.post(endpoint, json=kwargs)
                resp.raise_for_status()
                return resp.text

        return StructuredTool.from_function(
            coroutine=_invoke,
            name=name,
            description=description,
            args_schema=args_schema,
        )

    # ------------------------------------------------------------------
    # 내장 GraphRAG 스킬 등록
    # ------------------------------------------------------------------

    def register_graphrag_skills(self) -> None:
        """프롬프트 기반 내장 스킬을 등록합니다.

        외부 API 없이, 스킬별 전문 프롬프트 + GraphRAG 컨텍스트를 조합하여
        LLM이 직접 전문적인 답변을 생성합니다.

        반환값이 tool result로 LLM에 주입되어, LLM이 해당 지시에 따라 답변합니다.
        """
        import json as _json

        # 현재 사용자 ID를 스킬 호출 시 전달하기 위한 컨텍스트
        _current_user_id: list[str] = ["admin01"]

        def _set_user(uid: str) -> None:
            _current_user_id[0] = uid

        self._set_graphrag_user = _set_user

        def _search_graph(query: str, entity_type: str | None = None, n: int = 5) -> list[dict[str, Any]]:
            """GraphStore에서 엔티티를 검색하고, IAM 권한으로 필터링합니다."""
            try:
                from backend.config import settings
                from backend.graph.store import GraphStore
                from backend.core.iam import IAMEngine

                persist_path = settings.vault_root / ".graph" / "knowledge_graph.json"
                store = GraphStore(persist_path=persist_path)

                # IAM 엔진 로드
                iam: IAMEngine | None = None
                try:
                    iam = IAMEngine(settings.vault_root / "iam.yaml")
                except Exception:
                    pass

                user_id = _current_user_id[0]
                entities = store.search_entities(query=query, entity_type=entity_type, limit=n * 2)

                # admin 역할이면 IAM 체크 건너뜀
                is_admin = False
                if iam:
                    user_roles = iam.get_user_roles(user_id)
                    is_admin = "admin" in user_roles

                results = []
                denied_count = 0
                for e in entities:
                    # IAM 권한 체크 (admin은 전체 접근)
                    allowed_sources = e.source_paths[:3]
                    if iam and e.source_paths and not is_admin:
                        normalized = [p.lstrip("/") for p in e.source_paths]
                        allowed_sources = [p for p in normalized if iam.can_read(user_id, p)]
                        if not allowed_sources:
                            denied_count += 1
                            continue

                    # 보안등급 체크: Grade 3는 admin만 접근
                    sg = e.properties.get("security_grade", 1)
                    if sg >= 3 and not is_admin:
                        denied_count += 1
                        continue

                    entry: dict[str, Any] = {"name": e.name, "type": e.entity_type, "security_grade": sg}
                    for key in [
                        "description", "product_code", "rider_code",
                        "coverage_amount", "coverage_period", "payment_period",
                        "age_range", "renewal_type", "premium_type",
                        "surrender_type", "surrender_ratio", "effective_date",
                        "claim_conditions", "exclusions", "base_amount",
                        "sub_types", "parent_product", "waiting_period",
                        "underwriting_class", "version_label",
                        "mandatory_riders", "conversion_period",
                    ]:
                        val = e.properties.get(key)
                        if val:
                            entry[key] = val
                    sources = [
                        p.split("/")[-1].replace(".md", "").split("@")[0]
                        for p in allowed_sources[:3]
                    ]
                    if sources:
                        entry["sources"] = sources
                    results.append(entry)
                    if len(results) >= n:
                        break

                # 권한 없는 데이터가 있었다면 안내 추가
                if denied_count > 0:
                    results.append({
                        "name": f"[접근 제한 {denied_count}건]",
                        "type": "notice",
                        "description": f"권한이 없는 문서에서 {denied_count}건의 관련 정보가 발견되었으나 접근이 제한됩니다. 관리자에게 열람 권한을 요청하세요.",
                    })

                return results
            except Exception:
                return []

        def _build_prompt_skill(
            skill_name: str,
            display_name: str,
            description: str,
            expert_prompt: str,
            params_schema: dict[str, Any],
            search_type: str | None = None,
            use_graphrag: bool = True,
            category: str = "analysis",
        ) -> None:
            """프롬프트 기반 스킬 하나를 등록합니다.

            use_graphrag=True: GraphRAG에서 컨텍스트를 검색하여 프롬프트에 포함
            use_graphrag=False: 프롬프트만으로 LLM이 직접 답변 (번역, 계산 등)
            """

            async def _invoke(**kwargs: Any) -> str:
                prompt_parts = [
                    f"[{display_name}]\n{expert_prompt}\n",
                ]

                if use_graphrag:
                    query = " ".join(str(v) for v in kwargs.values() if v)
                    entities = _search_graph(query, entity_type=search_type, n=3)
                    context = _json.dumps(entities, ensure_ascii=False) if entities else "관련 데이터 없음"
                    # 컨텍스트가 너무 길면 잘라냄
                    if len(context) > 800:
                        context = context[:800] + "..."
                    prompt_parts.append(f"## 데이터\n{context}\n")
                    prompt_parts.append("위 데이터 기반으로 답변하세요. 없는 내용은 추측 금지.")
                else:
                    # GraphRAG 불필요 — 파라미터를 직접 전달
                    params_text = "\n".join(f"- {k}: {v}" for k, v in kwargs.items() if v)
                    prompt_parts.append(f"## 입력 정보\n{params_text}\n")
                    prompt_parts.append("위 정보를 바탕으로 답변하세요.")

                return "\n".join(prompt_parts)

            # Pydantic 스키마 빌드
            args_schema = self._build_pydantic_schema(params_schema)
            self._skills[skill_name] = {
                "name": skill_name,
                "display_name": display_name,
                "endpoint": "__prompt__",
                "depends_on": [],
                "description": description,
                "method": "POST",
                "params_schema": params_schema,
                "source": "__builtin__",
                "category": category,
            }
            self._tools[skill_name] = StructuredTool.from_function(
                coroutine=_invoke,
                name=skill_name,
                description=description,
                args_schema=args_schema,
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 프롬프트 기반 스킬 정의
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        _build_prompt_skill(
            skill_name="get-product-spec",
            display_name="상품 사양 조회",
            description="보험 상품 사양 조회 — 상품코드나 상품명으로 보장내용, 가입조건, 특약 정보를 안내합니다.",
            expert_prompt=(
                "당신은 보험 상품 전문 상담사입니다.\n"
                "검색된 상품 데이터를 바탕으로 다음을 체계적으로 안내하세요:\n"
                "1. 상품 개요 (상품명, 유형, 갱신/비갱신)\n"
                "2. 보장 내용 (보장항목, 보장금액, 보장기간)\n"
                "3. 가입 조건 (가입연령, 납입기간, 심사등급)\n"
                "4. 해약환급금 유형 (기본형/무해약환급금형 등)\n"
                "5. 포함 특약 목록\n"
                "표 형식을 적극 활용하세요."
            ),
            params_schema={
                "product_code": {"type": "string", "description": "상품 코드", "required": False},
                "product_name": {"type": "string", "description": "상품명", "required": False},
            },
            search_type="product",
            category="search",
        )

        _build_prompt_skill(
            skill_name="get-coverage",
            display_name="보장 내용 조회",
            description="보장 내용 조회 — 보장항목, 보험금 지급조건, 면책사항을 안내합니다.",
            expert_prompt=(
                "당신은 보험 보장분석 전문가입니다.\n"
                "검색된 데이터를 바탕으로 다음을 명확히 안내하세요:\n"
                "1. 보장항목별 지급금액과 지급조건\n"
                "2. 면책사항 및 감액기간\n"
                "3. 중복수술 지급 규칙 (있는 경우)\n"
                "4. 보장 시작일과 만기\n"
                "고객이 이해하기 쉽게 예시를 들어 설명하세요."
            ),
            params_schema={
                "query": {"type": "string", "description": "보장 내용 검색 쿼리 (예: 암진단금, 수술비)", "required": True},
            },
            search_type="coverage",
            category="search",
        )

        _build_prompt_skill(
            skill_name="explain-term",
            display_name="약관 용어 설명",
            description="약관 용어 설명 — 보험 전문용어를 고객이 이해하기 쉽게 풀어서 설명합니다.",
            expert_prompt=(
                "당신은 보험 약관 해설 전문가입니다.\n"
                "전문용어를 고객이 이해할 수 있도록 다음 형식으로 설명하세요:\n"
                "1. 한 줄 정의\n"
                "2. 쉬운 비유나 예시\n"
                "3. 관련 약관 조항 (있으면)\n"
                "4. 실무에서 자주 묻는 포인트\n"
                "어려운 법률 용어는 괄호 안에 풀이를 추가하세요."
            ),
            params_schema={
                "term": {"type": "string", "description": "설명이 필요한 보험 용어", "required": True},
            },
            search_type=None,
            category="search",
        )

        _build_prompt_skill(
            skill_name="compare-riders",
            display_name="특약 비교",
            description="특약 비교 — 여러 특약의 보장내용, 보험료, 가입조건을 비교표로 안내합니다.",
            expert_prompt=(
                "당신은 보험 특약 비교분석 전문가입니다.\n"
                "검색된 특약 데이터를 비교표 형태로 정리하세요:\n"
                "| 항목 | 특약A | 특약B | ... |\n"
                "비교 항목: 보장내용, 보장금액, 보장기간, 가입연령, 갱신여부, 보험료 수준\n"
                "마지막에 각 특약의 장단점을 간략히 요약하세요."
            ),
            params_schema={
                "rider_names": {"type": "string", "description": "비교할 특약명 (쉼표 구분)", "required": True},
            },
            search_type=None,
            category="analysis",
        )

        _build_prompt_skill(
            skill_name="search-regulation",
            display_name="규정/약관 검색",
            description="규정/약관 검색 — 보험 관련 규정, 법령, 약관 조항을 검색하고 요약합니다.",
            expert_prompt=(
                "당신은 보험법규 전문가입니다.\n"
                "검색된 규정/약관 데이터를 다음 형식으로 안내하세요:\n"
                "1. 해당 규정의 핵심 내용 요약\n"
                "2. 적용 대상 및 조건\n"
                "3. 시행일 (effective_date가 있으면 반드시 명시)\n"
                "4. 관련 조항 간 관계\n"
                "법률 용어는 쉽게 풀어서 설명하세요."
            ),
            params_schema={
                "query": {"type": "string", "description": "검색할 규정/약관 내용", "required": True},
            },
            search_type="regulation",
            category="search",
        )

        _build_prompt_skill(
            skill_name="document-summary",
            display_name="문서 요약",
            description="문서 요약 — 지정된 주제와 관련된 문서 내용을 검색하여 핵심을 요약합니다.",
            expert_prompt=(
                "당신은 문서 분석 전문가입니다.\n"
                "검색된 데이터를 바탕으로 다음을 수행하세요:\n"
                "1. 핵심 내용 3~5줄 요약\n"
                "2. 주요 키워드 나열\n"
                "3. 상세 내용 (구조화된 형태)\n"
                "출처 문서명을 반드시 언급하세요."
            ),
            params_schema={
                "query": {"type": "string", "description": "요약할 주제 또는 문서명", "required": True},
            },
            search_type=None,
            category="analysis",
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 프롬프트 전용 스킬 (GraphRAG 불필요)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        _build_prompt_skill(
            skill_name="translate",
            display_name="번역",
            description="번역 — 보험 문서나 약관을 한↔영 번역합니다.",
            expert_prompt=(
                "당신은 보험/금융 전문 번역가입니다.\n"
                "정확하고 자연스럽게 번역하세요.\n"
                "보험 전문용어는 업계 표준 번역을 사용하세요.\n"
                "원문의 의미를 훼손하지 않되, 대상 언어에 맞게 자연스럽게 표현하세요."
            ),
            params_schema={
                "text": {"type": "string", "description": "번역할 텍스트", "required": True},
                "target_lang": {"type": "string", "description": "대상 언어 (ko/en)", "required": False, "default": "ko"},
            },
            use_graphrag=False,
            category="analysis",
        )

        _build_prompt_skill(
            skill_name="draft-email",
            display_name="이메일 초안",
            description="이메일 초안 작성 — 고객 안내, 사내 공지 등 이메일 초안을 작성합니다.",
            expert_prompt=(
                "당신은 보험회사의 커뮤니케이션 전문가입니다.\n"
                "다음 원칙을 지켜 이메일을 작성하세요:\n"
                "1. 정중하고 명확한 어조\n"
                "2. 핵심 내용을 먼저, 부가 설명은 뒤에\n"
                "3. 필요한 첨부/행동 사항은 별도 안내\n"
                "4. 적절한 인사말과 맺음말 포함"
            ),
            params_schema={
                "purpose": {"type": "string", "description": "이메일 목적 (예: 보험금 지급 안내, 계약 변경 안내)", "required": True},
                "recipient": {"type": "string", "description": "수신자 (예: 고객, 팀원)", "required": False, "default": "고객"},
            },
            use_graphrag=False,
            category="analysis",
        )

        _build_prompt_skill(
            skill_name="calculate-simple",
            display_name="간단 계산",
            description="간단 계산 — 보험료, 환급금, 수익률 등을 간단히 계산합니다.",
            expert_prompt=(
                "당신은 보험 수리 전문가입니다.\n"
                "주어진 조건으로 계산을 수행하고 결과를 보여주세요.\n"
                "계산 과정을 단계별로 설명하세요.\n"
                "주의: 이것은 참고용 계산이며, 정확한 금액은 상품 약관을 확인해야 합니다."
            ),
            params_schema={
                "description": {"type": "string", "description": "계산 내용 (예: 월 보험료 5만원, 20년납, 해약환급금)", "required": True},
            },
            use_graphrag=False,
            category="analysis",
        )

        registered = [
            "get-product-spec", "get-coverage", "explain-term",
            "compare-riders", "search-regulation", "document-summary",
            "translate", "draft-email", "calculate-simple",
        ]
        logger.info("Registered %d prompt-based skills: %s", len(registered), registered)

    # ------------------------------------------------------------------
    # 코드 스킬: Python 코드 기반 동적 스킬
    # ------------------------------------------------------------------

    _CODE_SKILLS_DIR = Path(settings.vault_root).parent / "data" / "skills" / "custom"

    # 샌드박스 허용 모듈
    _ALLOWED_MODULES = frozenset({
        "math", "statistics", "datetime", "json", "re",
        "collections", "itertools", "functools", "decimal",
        "fractions", "random", "string", "textwrap",
    })

    def _load_code_skills(self) -> None:
        """data/skills/custom/*.py 코드 스킬을 로드합니다."""
        code_dir = self._CODE_SKILLS_DIR
        if not code_dir.exists():
            return

        for py_file in sorted(code_dir.glob("*.py")):
            try:
                self._load_code_skill(py_file)
            except Exception as e:
                logger.error("Failed to load code skill %s: %s", py_file.name, e)

    def _load_code_skill(self, path: Path) -> None:
        """단일 .py 코드 스킬 파일을 로드하여 등록합니다.

        코드 스킬 파일 형식:
        ```python
        # skill: my-calculator
        # display_name: 계산기
        # description: 보험료 복리 계산을 수행합니다
        # category: analysis
        # params: {"amount": {"type": "number", "description": "금액", "required": true}}

        def run(amount: float, rate: float = 0.03, years: int = 10) -> str:
            result = amount * (1 + rate) ** years
            return f"{years}년 후 적립금: {result:,.0f}원"
        ```
        """
        import json as _json

        source = path.read_text(encoding="utf-8")

        # 메타데이터 파싱 (# 주석 헤더)
        meta: dict[str, str] = {}
        for line in source.splitlines():
            if not line.startswith("# "):
                break
            parts = line[2:].split(":", 1)
            if len(parts) == 2:
                meta[parts[0].strip()] = parts[1].strip()

        skill_name = meta.get("skill", path.stem)
        display_name = meta.get("display_name", skill_name)
        description = meta.get("description", f"코드 스킬: {skill_name}")
        category = meta.get("category", "custom")

        # params 파싱
        params_str = meta.get("params", "{}")
        try:
            params_schema = _json.loads(params_str)
        except _json.JSONDecodeError:
            params_schema = {}

        # 샌드박스 실행 함수 생성
        async def _execute(**kwargs: Any) -> str:
            return self._run_code_sandbox(source, kwargs)

        args_schema = self._build_pydantic_schema(params_schema)

        self._skills[skill_name] = {
            "name": skill_name,
            "display_name": display_name,
            "endpoint": "__code__",
            "depends_on": [],
            "description": description,
            "method": "POST",
            "params_schema": params_schema,
            "source": str(path),
            "category": category,
        }
        self._tools[skill_name] = StructuredTool.from_function(
            coroutine=_execute,
            name=skill_name,
            description=description,
            args_schema=args_schema,
        )
        logger.info("Loaded code skill: %s (%s)", skill_name, display_name)

    @staticmethod
    def _validate_code_ast(source: str) -> list[str]:
        """AST를 파싱하여 위험한 코드 패턴을 탐지합니다."""
        import ast

        violations: list[str] = []
        lines = []
        header_done = False
        for line in source.splitlines():
            if not header_done and line.startswith("# "):
                continue
            header_done = True
            lines.append(line)
        code = "\n".join(lines)

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f"구문 오류: {e}"]

        _BLOCKED_NAMES = {"exec", "eval", "compile", "open", "__import__", "globals", "locals", "getattr", "setattr", "delattr"}
        _BLOCKED_MODULES = {"os", "sys", "subprocess", "shutil", "socket", "requests", "urllib", "http", "ctypes", "importlib"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in _BLOCKED_MODULES:
                        violations.append(f"차단된 모듈: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    if top in _BLOCKED_MODULES:
                        violations.append(f"차단된 모듈: {node.module}")
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in _BLOCKED_NAMES:
                    violations.append(f"차단된 함수: {func.id}()")
                elif isinstance(func, ast.Attribute) and func.attr in _BLOCKED_NAMES:
                    violations.append(f"차단된 함수: .{func.attr}()")

        return violations

    def _run_code_sandbox(self, source: str, params: dict[str, Any]) -> str:
        """제한된 샌드박스에서 Python 코드를 실행합니다."""
        import json as _json
        import subprocess as _subprocess
        import tempfile
        import os

        # AST 검증
        violations = self._validate_code_ast(source)
        if violations:
            return f"보안 검증 실패: {'; '.join(violations)}"

        allowed_set = repr(set(self._ALLOWED_MODULES))

        wrapper = (
            "import json\n"
            f"_ALLOWED = {allowed_set}\n"
            "_orig = __builtins__['__import__'] if isinstance(__builtins__, dict) else __builtins__.__import__\n"
            "def _safe_import(name, *args, **kwargs):\n"
            "    top = name.split('.')[0]\n"
            "    if top not in _ALLOWED and top != 'json':\n"
            "        raise ImportError(f'모듈 {top} 사용 불가')\n"
            "    return _orig(name, *args, **kwargs)\n"
            "if isinstance(__builtins__, dict):\n"
            "    __builtins__['__import__'] = _safe_import\n"
            "    for _b in ['exec','eval','compile','open','globals','locals']:\n"
            "        __builtins__.pop(_b, None)\n"
            "else:\n"
            "    __builtins__.__import__ = _safe_import\n"
            "\n"
        )

        # 사용자 코드 (메타 주석 제거)
        user_lines = []
        header_done = False
        for line in source.splitlines():
            if not header_done and line.startswith("# "):
                continue
            header_done = True
            user_lines.append(line)
        user_code = "\n".join(user_lines)

        # run() 호출부
        call_code = (
            f"\n\n_params = json.loads({_json.dumps(_json.dumps(params, ensure_ascii=False))})\n"
            "try:\n"
            "    _result = run(**_params)\n"
            "    print(json.dumps({'result': str(_result)}, ensure_ascii=False))\n"
            "except Exception as e:\n"
            "    print(json.dumps({'error': str(e)}, ensure_ascii=False))\n"
        )

        full_code = wrapper + user_code + call_code

        # 임시 파일에 쓰고 subprocess로 실행
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8",
            ) as tmp:
                tmp.write(full_code)
                tmp_path = tmp.name

            result = _subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=10,  # 10초 제한
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": os.environ.get("HOME", "/tmp"),
                    "LANG": "en_US.UTF-8",
                },
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()[-500:]
                return f"코드 실행 오류: {stderr}"

            stdout = result.stdout.strip()
            try:
                output = _json.loads(stdout)
                if "error" in output:
                    return f"실행 오류: {output['error']}"
                return output.get("result", stdout)
            except _json.JSONDecodeError:
                return stdout[:2000] if stdout else "결과 없음"

        except _subprocess.TimeoutExpired:
            return "코드 실행 시간 초과 (10초 제한)"
        except Exception as exc:
            return f"코드 실행 실패: {exc}"
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def create_code_skill(
        self,
        skill_name: str,
        display_name: str,
        description: str,
        code: str,
        params_schema: dict[str, Any],
        category: str = "custom",
    ) -> Path:
        """새 코드 스킬을 생성하고 파일로 저장합니다."""
        import json as _json

        code_dir = self._CODE_SKILLS_DIR
        code_dir.mkdir(parents=True, exist_ok=True)

        # 메타 헤더 + 코드
        header = (
            f"# skill: {skill_name}\n"
            f"# display_name: {display_name}\n"
            f"# description: {description}\n"
            f"# category: {category}\n"
            f"# params: {_json.dumps(params_schema, ensure_ascii=False)}\n"
        )
        full_content = header + "\n" + code.strip() + "\n"

        path = code_dir / f"{skill_name}.py"
        path.write_text(full_content, encoding="utf-8")

        # 즉시 등록
        self._load_code_skill(path)

        return path
