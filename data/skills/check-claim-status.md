---
created_at: '2026-03-19T09:00:00Z'
depends_on: []
description: 보험금 청구 상태 조회 - 청구번호로 진행 상태와 예상 지급일을 조회합니다.
endpoint: http://legacy-claims:8080/api/claim/status
method: GET
owner: admin01
inputs:
  claim_id:
    type: string
    description: "청구 번호"
    label: "청구번호"
outputs:
  status:
    type: string
    description: "처리 상태"
  expected_date:
    type: string
    description: "예상 지급일"
  handler:
    type: string
    description: "담당자"
params:
  claim_id:
    description: 청구 번호
    required: true
    type: string
  include_history:
    default: false
    description: 처리 이력 포함
    required: false
    type: boolean
skill_name: check-claim-status
type: skill
updated_at: '2026-03-19T09:00:00Z'
---

# 보험금 청구 상태 조회 (Check Claim Status)

## 개요

레거시 청구 시스템(legacy-claims)의 REST API를 호출하여 청구번호에 해당하는
보험금 청구 건의 현재 처리 상태, 담당자 정보, 예상 지급일을 조회합니다.

의존하는 선행 스킬이 없으며, 청구번호만 확보되면 독립적으로 호출 가능합니다.

## 실행 흐름

```
[check-claim-status]  ← 독립 실행 가능 (depends_on: [])
```

## 파라미터

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
| ---------- | ------ | ------ | -------- | ------ |
| claim_id | string | Y | — | 청구 번호 (예: CLM-2026-000123) |
| include_history | boolean | N | false | true 이면 처리 이력(상태 변경 로그) 포함 |

## 응답 형식

```json
{
  "claim_id": "CLM-2026-000123",
  "status": "REVIEWING",
  "status_label": "심사 중",
  "submitted_at": "2026-03-10T10:00:00Z",
  "last_updated_at": "2026-03-18T15:30:00Z",
  "expected_payout_date": "2026-03-25",
  "reviewer": {
    "id": "REV-042",
    "name": "김심사"
  },
  "history": [
    {
      "timestamp": "2026-03-10T10:00:00Z",
      "status": "SUBMITTED",
      "note": "청구 접수 완료"
    },
    {
      "timestamp": "2026-03-12T09:15:00Z",
      "status": "DOCUMENT_REQUESTED",
      "note": "추가 서류 요청: 진단서 원본"
    },
    {
      "timestamp": "2026-03-18T15:30:00Z",
      "status": "REVIEWING",
      "note": "서류 접수 완료, 심사 진행 중"
    }
  ]
}
```

> `include_history: false` 인 경우 `history` 필드는 응답에 포함되지 않습니다.

## 청구 상태 코드

| status | label | 설명 |
| -------- | ------- | ------ |
| SUBMITTED | 접수 완료 | 청구가 정상 접수됨 |
| DOCUMENT_REQUESTED | 서류 요청 | 추가 서류 제출 대기 중 |
| REVIEWING | 심사 중 | 손해사정사/심사팀 검토 중 |
| APPROVED | 지급 승인 | 지급 금액 확정, 이체 예정 |
| PAID | 지급 완료 | 계좌 이체 완료 |
| REJECTED | 부지급 | 면책 조항 또는 계약 조건 미충족 |
| CANCELLED | 취소 | 고객 요청 또는 중복 청구로 취소 |

## 에러 코드

| 코드 | HTTP 상태 | 설명 | 대응 |
| ------ | ----------- | ------ | ------ |
| C001 | 404 | 청구번호 미존재 | 청구번호 재확인 |
| C002 | 403 | 조회 권한 없음 | 고객 본인 확인 후 재요청 |
| C003 | 503 | 레거시 시스템 응답 없음 | 잠시 후 재시도 또는 수동 조회 요청 |
| C004 | 400 | claim_id 형식 오류 | CLM-YYYY-NNNNNN 형식 준수 |

## 사용 예시

```python
# 기본 조회 (이력 제외)
result = await check_claim_status_tool.ainvoke({
    "claim_id": "CLM-2026-000123"
})

# 처리 이력 포함 조회
result = await check_claim_status_tool.ainvoke({
    "claim_id": "CLM-2026-000123",
    "include_history": True
})
```

## 주의 사항

- `expected_payout_date` 는 심사 결과에 따라 변동될 수 있으며, 확정 지급일이 아닙니다.
- REJECTED 상태인 경우 이의신청은 별도 프로세스를 통해 처리합니다.
- 레거시 시스템의 응답 지연이 발생할 경우 최대 30초 타임아웃이 적용됩니다.
