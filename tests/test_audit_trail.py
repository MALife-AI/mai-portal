"""Tests for backend.security.audit_trail."""
import json
from pathlib import Path
from unittest.mock import patch

from backend.security.audit_trail import log_agent_response, get_audit_logs, AUDIT_DIR


def test_log_creates_file():
    log_agent_response(
        thread_id="test-thread-001",
        user_id="admin01",
        user_roles=["admin"],
        query="암진단금 보장 내용",
        referenced_sources=[
            {"name": "암진단특약", "type": "product", "source_titles": ["약관_2504"], "security_grade": 2},
        ],
        skills_used=["get-coverage"],
        security_grades=[2],
        response_preview="암진단금은...",
    )
    # 오늘 날짜 파일이 생성되었는지
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = AUDIT_DIR / f"audit_{today}.jsonl"
    assert log_file.exists()

    # 마지막 줄 파싱
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[-1])
    assert record["user_id"] == "admin01"
    assert record["query"] == "암진단금 보장 내용"
    assert record["max_security_grade"] == 2
    assert len(record["referenced_sources"]) == 1


def test_log_grade3_warning(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        log_agent_response(
            thread_id="test-thread-002",
            user_id="admin01",
            user_roles=["admin"],
            query="고객 질병이력",
            referenced_sources=[{"name": "고객정보", "security_grade": 3}],
            skills_used=[],
            security_grades=[3],
        )
    assert "Grade 3" in caplog.text


def test_get_audit_logs():
    # 위 테스트에서 기록한 로그가 조회되는지
    logs = get_audit_logs(limit=10)
    assert len(logs) >= 1
    assert any(l["thread_id"].startswith("test-thread") for l in logs)
