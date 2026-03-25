"""Tests for backend.agents.session_memory."""
import uuid
from backend.agents.session_memory import SessionMemory


def _unique_id():
    return f"test-{uuid.uuid4().hex[:8]}"


def test_save_and_recall():
    mem = SessionMemory(_unique_id())
    result = mem.save(summary="고객 무배당 건강보험 가입", content="2025년 가입, 월 보험료 5만원", category="customer_info")
    assert result["id"] == 1
    assert result["summary"] == "고객 무배당 건강보험 가입"

    all_text = mem.recall_all()
    assert "무배당 건강보험" in all_text

    detail = mem.recall_by_id(1)
    assert "2025년 가입" in detail

    found = mem.recall_by_keyword("건강보험")
    assert "무배당 건강보험" in found


def test_recall_not_found():
    mem = SessionMemory(_unique_id())
    assert "저장된 기억이 없습니다" in mem.recall_all()
    assert "찾을 수 없습니다" in mem.recall_by_id(999)


def test_context_summary():
    mem = SessionMemory(_unique_id())
    mem.save(summary="상품 선택: 암진단특약", content="보장금액 5천만원")
    mem.save(summary="가입 나이: 40세", content="남성")

    ctx = mem.get_context_summary(max_entries=5)
    assert "암진단특약" in ctx
    assert "40세" in ctx


def test_multiple_saves():
    mem = SessionMemory(_unique_id())
    for i in range(5):
        mem.save(summary=f"메모 {i}", content=f"내용 {i}")

    all_text = mem.recall_all()
    assert "메모 0" in all_text
    assert "메모 4" in all_text
