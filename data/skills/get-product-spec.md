---
created_at: '2026-01-12T09:00:00Z'
depends_on:
- validate-customer-info
description: 보험 상품 사양서 조회 - 상품코드로 요율표, 보장내용, 가입조건을 조회합니다.
endpoint: http://legacy-core:8080/api/product/spec
method: GET
owner: admin01
inputs:
  product_code:
    type: string
    description: "상품 코드"
    label: "상품코드"
outputs:
  product_name:
    type: string
    description: "상품명"
  coverage_details:
    type: object
    description: "보장 내용"
  rate_table:
    type: object
    description: "요율표"
params:
  include_rates:
    default: true
    description: 요율표 포함 여부
    required: false
    type: boolean
  product_code:
    description: 보험 상품 코드
    required: true
    type: string
skill_name: get-product-spec
type: skill
updated_at: '2026-03-10T14:30:00Z'
---

# 보험 상품 사양서 조회 (Get Product Spec)

## 개요
상품 코드 기반으로 레거시 상품 마스터에서 사양서를 조회합니다.

## 의존성
1. **validate-customer-info**: 고객의 가입 적격 상품 목록을 먼저 확인합니다.

## 조회 항목
- 상품명, 상품코드, 주계약/특약 구분
- 보장 내용 및 금액
- 가입 연령/기간 제한
- 보험료 요율표 (include_rates=true 시)

## 에러 코드
| 코드 | 설명 |
| ------ | ------ |
| P001 | 상품 코드 미존재 |
| P002 | 판매 중단 상품 |
| P003 | 요율표 미등록 |
