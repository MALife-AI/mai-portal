---
type: skill
skill_name: validate-customer-info
description: "고객 정보 유효성 검증 - 고객번호로 기본 정보를 조회하고 계약 적격성을 검증합니다."
endpoint: "http://legacy-core:8080/api/customer/validate"
method: POST
depends_on: []
inputs:
  customer_id:
    type: string
    description: "고객 번호"
    label: "고객번호"
outputs:
  customer_name:
    type: string
    description: "고객명"
  is_valid:
    type: boolean
    description: "유효 여부"
  eligible_products:
    type: array
    description: "가입 가능 상품 목록"
params:
  customer_id:
    type: string
    required: true
    description: "고객 번호"
  validation_type:
    type: string
    required: false
    description: "검증 유형 (basic, full)"
    default: "basic"
owner: admin01
created_at: "2026-01-10T09:00:00Z"
updated_at: "2026-03-10T14:30:00Z"
---

# 고객 정보 유효성 검증 (Validate Customer Info)

## 개요
레거시 코어 시스템의 고객 마스터 DB를 조회하여 기본 정보와 계약 적격성을 검증합니다.

## 검증 항목
- 고객번호 존재 여부
- 본인인증 완료 상태
- 제재/블랙리스트 대상 여부
- 보험 가입 연령 적격성

## 응답 형식
```json
{
  "valid": true,
  "customer_name": "홍길동",
  "age": 35,
  "risk_flags": [],
  "eligible_products": ["종신보험", "건강보험", "연금보험"]
}
```
