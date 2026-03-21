---
type: skill
skill_name: skill-maker
description: "스킬 생성 — 사용자의 요청을 분석하여 새로운 스킬을 자동으로 생성합니다. '~하는 스킬 만들어줘'라고 요청하면 스킬 이름, 설명, 엔드포인트, 파라미터를 자동 구성하여 등록합니다."
endpoint: http://localhost:9001/api/v1/skills/create
method: POST
owner: admin01
category: custom
depends_on: []
params:
  skill_name:
    type: string
    description: "생성할 스킬의 고유 ID (영문, 하이픈). 예: check-claim-status"
    required: true
  description:
    type: string
    description: "스킬 설명 (LLM이 호출 판단에 사용). 구체적이고 도메인 특화된 설명"
    required: true
  endpoint:
    type: string
    description: "호출할 API 엔드포인트 URL"
    required: true
  method:
    type: string
    description: "HTTP 메서드 (GET 또는 POST). 기본 POST"
    required: false
  category:
    type: string
    description: "카테고리: custom, search, analysis, report"
    required: false
  params:
    type: object
    description: "파라미터 스키마. 예: {\"query\": {\"type\": \"string\", \"required\": true, \"description\": \"검색어\"}}"
    required: false
  body:
    type: string
    description: "스킬 상세 설명 (마크다운)"
    required: false
created_at: '2026-03-21T00:00:00Z'
updated_at: '2026-03-21T00:00:00Z'
---

# 스킬 메이커 (Skill Maker)

## 개요

사용자의 자연어 요청을 분석하여 새로운 스킬을 자동으로 생성하는 메타 스킬입니다.

## 사용 예시

사용자가 에이전트에게 다음과 같이 요청하면:

- "고객 청구 상태를 조회하는 스킬 만들어줘"
- "일간 리포트를 생성하는 스킬 만들어줘"
- "상품코드로 약관을 검색하는 스킬 만들어줘"

에이전트가 자동으로:
1. 적절한 skill_name 생성 (예: `check-claim-status`)
2. 구체적인 description 작성
3. endpoint URL 설정
4. 필요한 파라미터 스키마 구성
5. 카테고리 분류
6. 스킬 등록

## 생성된 스킬 확인

생성 후 **스킬** 페이지 → **스킬 관리** 탭에서 확인하고, 노코드 에디터로 수정할 수 있습니다.
