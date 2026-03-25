"""Audit Trail: 에이전트 응답의 참조 문서/페이지/권한을 상세 기록.

금융감독원 가이드라인 준수를 위한 '답변 근거' 명확화:
  - 참조된 문서명, 페이지, 보안등급
  - 질의 시점의 사용자 권한
  - 답변에 사용된 스킬 목록
  - 타임스탬프 + 스레드 ID
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings

logger = logging.getLogger(__name__)

AUDIT_DIR = Path(settings.vault_root).parent / "data" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def log_agent_response(
    *,
    thread_id: str,
    user_id: str,
    user_roles: list[str],
    query: str,
    referenced_sources: list[dict[str, Any]],
    skills_used: list[str],
    security_grades: list[int],
    response_preview: str = "",
) -> None:
    """에이전트 응답에 대한 감사 기록을 저장합니다.

    Args:
        thread_id: 대화 스레드 ID
        user_id: 사용자 ID
        user_roles: 질의 시점의 사용자 역할
        query: 원본 질문
        referenced_sources: 참조된 소스 노드 [{name, type, source_titles, page_start, security_grade}]
        skills_used: 사용된 스킬 이름 목록
        security_grades: 참조된 문서의 보안등급 목록
        response_preview: 응답 미리보기 (200자)
    """
    timestamp = datetime.now(timezone.utc)
    record = {
        "timestamp": timestamp.isoformat(),
        "thread_id": thread_id,
        "user_id": user_id,
        "user_roles": user_roles,
        "query": query[:500],
        "response_preview": response_preview[:200],
        "referenced_sources": [
            {
                "name": s.get("name", ""),
                "type": s.get("type", ""),
                "source_titles": s.get("source_titles", []),
                "page_start": s.get("page_start"),
                "page_end": s.get("page_end"),
                "security_grade": s.get("security_grade", 1),
                "match_reason": s.get("match_reason", ""),
            }
            for s in referenced_sources
        ],
        "skills_used": skills_used,
        "max_security_grade": max(security_grades) if security_grades else 1,
        "access_control": {
            "grade_2_accessed": 2 in security_grades,
            "grade_3_accessed": 3 in security_grades,
        },
    }

    # 일별 로그 파일
    log_file = AUDIT_DIR / f"audit_{timestamp.strftime('%Y-%m-%d')}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Grade 3 접근 시 별도 경고 로그
    if 3 in security_grades:
        logger.warning(
            "AUDIT: Grade 3 data accessed — user=%s query='%s' sources=%s",
            user_id, query[:50], [s.get("name") for s in referenced_sources],
        )


def get_audit_logs(
    date: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """감사 로그를 조회합니다."""
    logs: list[dict[str, Any]] = []

    if date:
        log_file = AUDIT_DIR / f"audit_{date}.jsonl"
        if log_file.exists():
            for line in log_file.read_text(encoding="utf-8").strip().splitlines():
                try:
                    record = json.loads(line)
                    if user_id and record.get("user_id") != user_id:
                        continue
                    logs.append(record)
                except json.JSONDecodeError:
                    continue
    else:
        # 최근 로그 파일에서
        for log_file in sorted(AUDIT_DIR.glob("audit_*.jsonl"), reverse=True)[:7]:
            for line in log_file.read_text(encoding="utf-8").strip().splitlines():
                try:
                    record = json.loads(line)
                    if user_id and record.get("user_id") != user_id:
                        continue
                    logs.append(record)
                except json.JSONDecodeError:
                    continue
            if len(logs) >= limit:
                break

    return logs[-limit:]
