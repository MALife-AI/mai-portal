---
created_at: '2026-01-15T09:00:00Z'
depends_on:
- validate-customer-info
- get-product-spec
description: 보험료 산출 스킬 - 상품코드와 피보험자 정보를 기반으로 보험료를 계산합니다.
endpoint: http://legacy-core:8080/api/premium/calculate
method: POST
owner: admin01
params:
  coverage_amount:
    description: 보장금액 (원)
    required: true
    type: number
  insured_age:
    description: 피보험자 나이
    required: true
    type: integer
  payment_period:
    description: 납입기간 (년)
    required: true
    type: integer
  product_code:
    description: 보험 상품 코드
    required: true
    type: string
  rider_codes:
    description: 특약 코드 목록
    required: false
    type: array
skill_name: calculate-insurance-premium
type: skill
updated_at: '2026-03-10T14:30:00Z'
---

# 보험료 산출 (Calculate Insurance Premium)

## 개요
보험료 산출 스킬은 레거시 코어 시스템의 보험료 계산 API를 호출합니다.

## 의존성
1. **validate-customer-info**: 고객 정보 유효성 검증을 먼저 수행합니다.
2. **get-product-spec**: 상품 사양서를 조회하여 요율표를 가져옵니다.

## 실행 흐름
```
[validate-customer-info] → [get-product-spec] → [calculate-insurance-premium]
```

## 에러 처리
| 에러 코드 | 설명 | 대응 |
| ----------- | ------ | ------ |
| E001 | 상품 코드 미존재 | 유효한 상품 코드 확인 |
| E002 | 나이 범위 초과 | 가입 가능 연령 확인 |
| E003 | 요율표 미적용 | 관리자에게 요율 등록 요청 |
