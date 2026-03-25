"""Tests for backend.security.data_classification."""
from backend.security.data_classification import (
    classify_document,
    SecurityGrade,
    check_rag_access,
    get_grade_policy,
)


def test_grade1_general_document():
    content = "보험 약관에서 해약환급금이란 보험계약을 해약할 때 돌려받는 금액입니다."
    result = classify_document(content)
    assert result.grade == SecurityGrade.GRADE_1
    assert result.policy["learning_allowed"] is True
    assert result.policy["rag_allowed"] is True


def test_grade2_internal_document():
    content = "본 사업방법서는 보험상품의 인수기준을 규정합니다. 언더라이팅 가이드라인에 따라..."
    result = classify_document(content)
    assert result.grade == SecurityGrade.GRADE_2
    assert result.policy["learning_allowed"] is False
    assert result.policy["rag_allowed"] is True


def test_grade2_from_filepath():
    content = "상품 설계 관련 내용입니다."
    result = classify_document(content, "사업방법서_무배당건강보험.md")
    assert result.grade == SecurityGrade.GRADE_2


def test_grade3_personal_info():
    content = "고객번호 C12345, 주민등록번호 900101-1234567, 질병 이력 확인"
    result = classify_document(content)
    assert result.grade == SecurityGrade.GRADE_3
    assert result.policy["learning_allowed"] is False
    assert result.policy["rag_allowed"] is False
    assert result.policy["anonymize_required"] is True


def test_grade3_medical_history():
    content = "해당 고객의 질병 이력: 당뇨병 진단 (2022년), 사고 이력 없음"
    result = classify_document(content)
    assert result.grade == SecurityGrade.GRADE_3


def test_rag_access_grade1():
    assert check_rag_access(1, ["viewer"]) is True


def test_rag_access_grade2():
    assert check_rag_access(2, ["viewer"]) is True


def test_rag_access_grade3_viewer():
    assert check_rag_access(3, ["viewer"]) is False


def test_rag_access_grade3_admin():
    assert check_rag_access(3, ["admin"]) is True


def test_get_grade_policy():
    p1 = get_grade_policy(1)
    assert p1["learning_allowed"] is True
    p3 = get_grade_policy(3)
    assert p3["learning_allowed"] is False
    assert p3["anonymize_required"] is True
