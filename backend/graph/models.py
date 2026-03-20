from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Entity:
    """그래프 노드: 보험 도메인 특화 엔티티.

    엔티티 타입:
    - product: 보험상품/특약
    - coverage: 보장항목 (암진단금, 수술비 등)
    - condition: 질병/상해 (암, 뇌혈관질환 등)
    - regulation: 규정/법령/약관조항
    - organization: 회사/기관
    - person: 사람/역할
    - term: 전문용어/정의
    - document: 문서/자료

    properties 주요 키 (보험 도메인):
    - product_code: 상품코드 (A3756 등)
    - rider_code: 보종코드 (85044 등)
    - coverage_amount: 보장금액
    - coverage_period: 보장기간 (90세만기, 종신 등)
    - payment_period: 보험료납입기간 (10년납 등)
    - payment_frequency: 납입주기 (월납 등)
    - waiting_period: 면책/감액기간
    - renewal_type: 갱신형/비갱신형
    - age_range: 가입연령 범위
    - underwriting_class: 심사등급 (간편고지, 표준체 등)
    - premium_type: 보험료 유형 (자연식/평준)
    - surrender_type: 해약환급금 유형 (기본형/해약환급금이 없는 유형)
    - surrender_ratio: 해약환급금 비율 (기본형의 50% 등)
    - base_amount: 기준가입금액 (10만원 등)
    - sub_types: 세부유형 (1종~5종 등)
    - parent_product: 종속 주계약명
    - claim_conditions: 보험금 지급조건
    - exclusions: 면책사항
    - duplicate_surgery_rule: 중복수술 지급규칙
    - effective_date: 시행일/적용일
    - document_type: 출처 문서유형 (약관/사업방법서/산출방법서)
    - rate_reference: 적용위험률 출처
    - expense_ratio: 사업비율
    - mandatory_riders: 의무동시가입 특약
    - conversion_period: 일반심사보험 전환기간
    - revival_period: 부활 가능기간
    - source_document: 출처 문서명
    - description: 설명
    """

    id: str
    name: str
    entity_type: str
    properties: dict[str, Any] = field(default_factory=dict)
    source_paths: list[str] = field(default_factory=list)
    mentions: int = 0


@dataclass
class Relationship:
    """그래프 엣지: 엔티티 간 관계.

    관계 타입:
    - covers: 보장 (상품→보장항목)
    - includes: 포함 (상품→특약)
    - excludes: 제외/면책 (상품→질병)
    - requires: 요건 (상품→가입조건)
    - depends_on: 의존
    - regulates: 규제 (법령→상품)
    - belongs_to: 소속 (특약→상품)
    - references: 참조 (문서→문서)
    - provides: 제공 (기관→상품)
    - defines: 정의 (약관→용어)
    - diagnoses: 진단 (질병→보장항목)
    - pays: 지급 (보장항목→금액조건)
    - renews_as: 갱신관계
    - supersedes: 대체 (신규→구버전)
    - must_coexist: 의무동시가입 (특약↔특약)
    - converts_to: 전환 (간편고지→일반심사)
    """

    source_id: str
    target_id: str
    relation_type: str
    properties: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""
    weight: float = 1.0


@dataclass
class Community:
    """그래프 커뮤니티: 밀접 연결된 엔티티 그룹."""

    id: str
    name: str
    entity_ids: list[str] = field(default_factory=list)
    summary: str = ""
    level: int = 0
