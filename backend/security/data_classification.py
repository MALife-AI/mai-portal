"""Data Classification: 문서 보안등급 자동 분류 + 정책 엔진.

보안등급 체계:
  Grade 1 (학습용): 보험 용어, 일반 상담 스크립트, 공개 약관
    → SLM 학습 가능, 비식별화, 외부망 차단
  Grade 2 (참조용): 사규, UW 가이드라인, 보상 매뉴얼
    → Graph RAG 검색만 허용, 학습 금지, 권한 필터링
  Grade 3 (민감형): 고객 식별 정보, 질병 및 사고 이력
    → 활용 제한, 학습 금지, 가명/익명화 후 활용
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)


class SecurityGrade(IntEnum):
    """보안등급."""
    GRADE_1 = 1  # 학습용 (공개)
    GRADE_2 = 2  # 참조용 (사내)
    GRADE_3 = 3  # 민감형 (제한)


@dataclass
class ClassificationResult:
    """분류 결과."""
    grade: SecurityGrade
    reason: str
    detected_patterns: list[str]
    policy: dict[str, bool]  # learning_allowed, rag_allowed, external_allowed


# ── Grade 3 (민감형) 패턴 ─────────────────────────────────────────────────────
_GRADE3_PATTERNS = [
    # 개인정보
    r'\d{6}[-]\d{7}',           # 주민등록번호
    r'\d{3}[-]\d{2}[-]\d{5}',   # 사업자등록번호
    r'\d{4}[-]\d{4}[-]\d{4}[-]\d{4}',  # 카드번호
    r'010[-]\d{4}[-]\d{4}',     # 전화번호
    # 의료/질병
    r'질병\s*이력', r'사고\s*이력', r'진단\s*내역', r'치료\s*이력',
    r'고객\s*(?:번호|ID|아이디)', r'증권\s*번호', r'계약\s*번호',
    r'피보험자\s*(?:이름|성명|주소)', r'수익자\s*(?:이름|성명)',
    # 금융
    r'계좌\s*번호', r'보험금\s*(?:청구|지급)\s*내역',
]

# ── Grade 2 (참조용) 패턴 ─────────────────────────────────────────────────────
_GRADE2_PATTERNS = [
    r'사규', r'사업방법서', r'내규', r'매뉴얼',
    r'언더라이팅\s*(?:기준|가이드)', r'UW\s*(?:기준|가이드)',
    r'보상\s*(?:기준|매뉴얼|가이드)', r'심사\s*(?:기준|규정)',
    r'대외비', r'사내\s*한정', r'내부\s*(?:문서|자료)',
    r'산출방법서', r'요율\s*(?:표|기준)',
]

# ── 정책 매핑 ──────────────────────────────────────────────────────────────────
_GRADE_POLICIES = {
    SecurityGrade.GRADE_1: {
        "learning_allowed": True,     # SLM 학습 가능
        "rag_allowed": True,          # RAG 검색 가능
        "external_allowed": False,    # 외부망 차단
        "anonymize_required": True,   # 비식별화 필요
    },
    SecurityGrade.GRADE_2: {
        "learning_allowed": False,    # 학습 금지
        "rag_allowed": True,          # RAG 검색만 허용
        "external_allowed": False,    # 외부망 차단
        "anonymize_required": False,  # 원본 참조 가능 (권한 필터링)
    },
    SecurityGrade.GRADE_3: {
        "learning_allowed": False,    # 학습 금지
        "rag_allowed": False,         # RAG 직접 참조 금지
        "external_allowed": False,    # 외부망 차단
        "anonymize_required": True,   # 가명/익명화 후 활용
    },
}


def classify_document(content: str, file_path: str = "") -> ClassificationResult:
    """문서 내용을 분석하여 보안등급을 자동 분류합니다.

    분류 우선순위: Grade 3 > Grade 2 > Grade 1
    """
    detected: list[str] = []
    text = content[:5000]  # 상위 5000자만 스캔

    # Grade 3 체크
    for pattern in _GRADE3_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            detected.append(f"G3:{pattern}")
            if len(detected) >= 2:
                return ClassificationResult(
                    grade=SecurityGrade.GRADE_3,
                    reason="민감 개인정보/의료정보 감지",
                    detected_patterns=detected,
                    policy=_GRADE_POLICIES[SecurityGrade.GRADE_3],
                )

    # 단일 Grade 3 패턴도 민감형
    if detected:
        return ClassificationResult(
            grade=SecurityGrade.GRADE_3,
            reason="개인정보 패턴 감지",
            detected_patterns=detected,
            policy=_GRADE_POLICIES[SecurityGrade.GRADE_3],
        )

    # Grade 2 체크
    for pattern in _GRADE2_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            detected.append(f"G2:{pattern}")

    # 파일 경로 기반 분류
    path_lower = file_path.lower()
    if any(kw in path_lower for kw in ["사업방법서", "산출방법서", "uw", "내규"]):
        detected.append("G2:filepath")

    if detected:
        return ClassificationResult(
            grade=SecurityGrade.GRADE_2,
            reason="사규/가이드라인/내부문서 감지",
            detected_patterns=detected,
            policy=_GRADE_POLICIES[SecurityGrade.GRADE_2],
        )

    # 기본: Grade 1
    return ClassificationResult(
        grade=SecurityGrade.GRADE_1,
        reason="일반 공개 문서",
        detected_patterns=[],
        policy=_GRADE_POLICIES[SecurityGrade.GRADE_1],
    )


def get_grade_policy(grade: int) -> dict[str, bool]:
    """등급별 정책을 반환합니다."""
    return _GRADE_POLICIES.get(SecurityGrade(grade), _GRADE_POLICIES[SecurityGrade.GRADE_1])


def check_rag_access(grade: int, user_roles: list[str]) -> bool:
    """RAG 검색 시 해당 등급의 문서에 접근 가능한지 확인합니다."""
    policy = get_grade_policy(grade)

    if not policy["rag_allowed"]:
        # Grade 3: admin만 가명화된 데이터에 접근 가능
        return "admin" in user_roles

    return True  # Grade 1, 2는 RAG 허용 (IAM 권한은 별도 체크)
