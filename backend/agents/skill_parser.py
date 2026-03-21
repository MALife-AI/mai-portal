"""Skill Parser: type:skill 마크다운 → LangChain Tool 동적 변환."""
from __future__ import annotations

import logging
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
        skills_dir = self._skills_dir
        if not skills_dir.exists():
            return

        for md_file in skills_dir.glob("**/*.md"):
            try:
                self._load_skill(md_file)
            except Exception as e:
                logger.error("Failed to load skill %s: %s", md_file, e)

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
