"""Legacy Adapter API."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class LegacyRequest(BaseModel):
    system: str
    path: str
    payload: dict


@router.post("/call")
async def call_legacy(
    body: LegacyRequest,
    user_id: str = Depends(get_current_user),
):
    from backend.adapters.legacy import LegacyAdapter

    # 허용된 레거시 시스템만 접근 가능
    _ALLOWED_SYSTEMS = {"core", "uw", "policy", "claim", "customer"}
    if body.system not in _ALLOWED_SYSTEMS:
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(400, f"허용되지 않은 시스템: {body.system}. 허용: {_ALLOWED_SYSTEMS}")
    adapter = LegacyAdapter(base_url=f"http://legacy-{body.system}:8080")
    result = await adapter.call(body.path, body.payload)
    return result


# ─── 언더라이팅 심사 ──────────────────────────────────────────────────────────


class UnderwritingRequest(BaseModel):
    customer_id: str = Field(..., description="고객 번호")
    product_code: str = Field(..., description="가입 신청 상품 코드")
    sum_insured: float | None = Field(None, description="가입금액 (원)")


class DiseaseRecord(BaseModel):
    disease_code: str
    disease_name: str
    diagnosed_date: str
    status: str  # active / cured / chronic
    severity: str  # mild / moderate / severe


class OccupationInfo(BaseModel):
    occupation_code: str
    occupation_name: str
    risk_grade: str  # 1급~5급


class ExistingPolicy(BaseModel):
    policy_no: str
    product_name: str
    insurer: str  # 자사 / 타사명
    sum_insured: float
    status: str  # active / lapsed
    start_date: str


class UnderwritingData(BaseModel):
    """레거시 시스템들로부터 수집한 언더라이팅 원천 데이터."""
    customer_id: str
    customer_name: str
    age: int
    gender: str
    disease_history: list[DiseaseRecord]
    occupation: OccupationInfo
    own_policies: list[ExistingPolicy]
    other_policies: list[ExistingPolicy]
    total_sum_insured_own: float
    total_sum_insured_other: float


async def _fetch_underwriting_data(
    req: UnderwritingRequest,
) -> UnderwritingData:
    """레거시 시스템에서 고객 정보 + 언더라이팅 데이터 일괄 수집.

    고객번호 하나로 다음을 병렬 조회합니다:
      - 고객 기본정보 (나이, 성별, 직업)
      - 질병이력
      - 자사 기가입 내역
      - 타사 가입 내역

    실제 환경에서는 각 레거시 시스템을 병렬 호출합니다.
    현재는 시뮬레이션 데이터를 반환합니다.
    """
    from backend.adapters.legacy import LegacyAdapter

    # 실제 구현 시 병렬 호출:
    # adapter = LegacyAdapter(base_url="http://legacy-core:8080")
    # customer_task = adapter.call("/customer/info", {"customer_id": req.customer_id})
    # disease_task = adapter.call("/uw/disease-history", {"customer_id": req.customer_id})
    # occupation_task = adapter.call("/uw/occupation", {"customer_id": req.customer_id})
    # own_policy_task = adapter.call("/uw/own-policies", {"customer_id": req.customer_id})
    # other_policy_task = adapter.call("/uw/other-policies", {"customer_id": req.customer_id})
    # cust_resp, disease_resp, occ_resp, own_resp, other_resp = await asyncio.gather(
    #     customer_task, disease_task, occupation_task, own_policy_task, other_policy_task
    # )

    # ── 시뮬레이션 데이터 ──
    await asyncio.sleep(0.1)  # 네트워크 호출 시뮬레이션

    return UnderwritingData(
        customer_id=req.customer_id,
        customer_name=f"고객_{req.customer_id}",
        age=45,
        gender="M",
        disease_history=[
            DiseaseRecord(
                disease_code="E11",
                disease_name="제2형 당뇨병",
                diagnosed_date="2022-03-15",
                status="chronic",
                severity="moderate",
            ),
        ],
        occupation=OccupationInfo(
            occupation_code="OCC_0101",
            occupation_name="사무직",
            risk_grade="1급",
        ),
        own_policies=[
            ExistingPolicy(
                policy_no="MA-2024-001234",
                product_name="무배당 건강보험",
                insurer="자사",
                sum_insured=50_000_000,
                status="active",
                start_date="2024-01-10",
            ),
        ],
        other_policies=[
            ExistingPolicy(
                policy_no="OT-2023-005678",
                product_name="종합보험",
                insurer="한화생명",
                sum_insured=30_000_000,
                status="active",
                start_date="2023-06-01",
            ),
        ],
        total_sum_insured_own=50_000_000,
        total_sum_insured_other=30_000_000,
    )


def _build_uw_assessment(data: UnderwritingData, product_code: str, sum_insured: float | None) -> dict[str, Any]:
    """수집된 데이터를 기반으로 룰 기반 사전 심사 수행."""

    risk_factors: list[str] = []
    warnings: list[str] = []
    decision = "standard"  # standard / substandard / decline / refer

    # ── 질병이력 심사 ──
    for d in data.disease_history:
        if d.status == "chronic":
            risk_factors.append(f"만성 질환: {d.disease_name} ({d.diagnosed_date} 진단)")
            if d.severity == "severe":
                decision = "decline"
                warnings.append(f"{d.disease_name} 중증 — 인수 거절 사유")
            elif d.severity == "moderate":
                if decision == "standard":
                    decision = "substandard"
                warnings.append(f"{d.disease_name} 중등도 — 할증 또는 부담보 검토 필요")
        elif d.status == "active":
            risk_factors.append(f"치료 중: {d.disease_name}")
            decision = "refer"
            warnings.append(f"{d.disease_name} 치료 중 — 전문 심사 필요")

    # ── 직업 위험도 ──
    occ = data.occupation
    occ_grade = int(occ.risk_grade.replace("급", ""))
    if occ_grade >= 4:
        risk_factors.append(f"고위험 직업: {occ.occupation_name} ({occ.risk_grade})")
        if decision == "standard":
            decision = "substandard"
        warnings.append(f"직업 {occ.risk_grade} — 할증 적용 대상")
    elif occ_grade >= 3:
        risk_factors.append(f"중위험 직업: {occ.occupation_name} ({occ.risk_grade})")

    # ── 나이 심사 ──
    if data.age >= 65:
        risk_factors.append(f"고령: {data.age}세")
        warnings.append("65세 이상 — 가입 한도 및 보장 범위 확인 필요")
    elif data.age >= 55:
        risk_factors.append(f"준고령: {data.age}세")

    # ── 가입금액 한도 심사 ──
    requested = sum_insured or 0
    total_existing = data.total_sum_insured_own + data.total_sum_insured_other
    total_after = total_existing + requested

    if total_after > 500_000_000:
        warnings.append(
            f"총 가입금액 {total_after/1e8:.1f}억 — 5억 초과, 대면 심사 필요"
        )
        if decision in ("standard", "substandard"):
            decision = "refer"
    elif total_after > 300_000_000:
        warnings.append(f"총 가입금액 {total_after/1e8:.1f}억 — 3억 초과 주의")

    # ── 기가입 중복 체크 ──
    all_policies = data.own_policies + data.other_policies
    active_count = sum(1 for p in all_policies if p.status == "active")
    if active_count >= 5:
        warnings.append(f"유지 중 계약 {active_count}건 — 다건 가입 심사 기준 확인")

    decision_label = {
        "standard": "표준체 인수",
        "substandard": "조건부 인수 (할증/부담보)",
        "decline": "인수 거절",
        "refer": "전문 심사 회부",
    }

    return {
        "decision": decision,
        "decision_label": decision_label.get(decision, decision),
        "risk_factors": risk_factors,
        "warnings": warnings,
        "summary": {
            "customer": f"{data.customer_name} ({data.gender}/{data.age}세)",
            "product_code": product_code,
            "occupation": f"{occ.occupation_name} ({occ.risk_grade})",
            "disease_count": len(data.disease_history),
            "chronic_conditions": [d.disease_name for d in data.disease_history if d.status == "chronic"],
            "own_policy_count": len(data.own_policies),
            "other_policy_count": len(data.other_policies),
            "total_sum_insured": total_existing,
            "requested_sum_insured": requested,
            "total_after_new": total_after,
        },
    }


@router.post("/underwriting", summary="언더라이팅 사전심사")
async def underwriting_assessment(
    req: UnderwritingRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """고객번호로 레거시 시스템에서 심사 원천데이터를 일괄 수집하고 사전심사를 수행합니다.

    고객번호 기반 자동 수집 항목:
      - 고객 기본정보 (나이, 성별)
      - 질병이력 (질병코드, 진단일, 상태, 중증도)
      - 직업 정보 (직업코드, 위험등급)
      - 자사 기가입 내역
      - 타사 가입 내역

    심사 결과:
      - standard: 표준체 인수
      - substandard: 조건부 인수 (할증/부담보)
      - decline: 인수 거절
      - refer: 전문 심사 회부
    """
    # 1) 고객번호로 레거시 시스템에서 데이터 일괄 수집
    uw_data = await _fetch_underwriting_data(req)

    # 2) 룰 기반 사전심사
    assessment = _build_uw_assessment(uw_data, req.product_code, req.sum_insured)

    # 3) 원천 데이터 + 심사 결과 반환
    return {
        "assessment": assessment,
        "collected_data": {
            "customer_info": {
                "customer_id": uw_data.customer_id,
                "customer_name": uw_data.customer_name,
                "age": uw_data.age,
                "gender": uw_data.gender,
            },
            "disease_history": [d.model_dump() for d in uw_data.disease_history],
            "occupation": uw_data.occupation.model_dump(),
            "own_policies": [p.model_dump() for p in uw_data.own_policies],
            "other_policies": [p.model_dump() for p in uw_data.other_policies],
        },
    }
