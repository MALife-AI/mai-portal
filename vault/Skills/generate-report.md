---
created_at: '2026-03-19T09:00:00Z'
depends_on: []
description: 리포트 생성 - 실적/통계 데이터를 기반으로 마크다운 리포트를 자동 생성합니다.
endpoint: http://legacy-reporting:8080/api/report/generate
method: POST
owner: admin01
params:
  date_range:
    description: '조회 기간 {start: ''YYYY-MM-DD'', end: ''YYYY-MM-DD''}'
    required: true
    type: object
  metrics:
    description: 포함할 지표 목록. 미지정 시 리포트 유형의 기본 지표 전체 포함
    required: false
    type: array
  report_type:
    description: 리포트 유형 (daily, weekly, monthly)
    required: true
    type: string
skill_name: generate-report
type: skill
updated_at: '2026-03-19T09:00:00Z'
---

# 리포트 생성 (Generate Report)

## 개요

레거시 리포팅 시스템(legacy-reporting)의 집계 API를 호출하여
일간/주간/월간 실적 및 통계 데이터를 마크다운 형식의 리포트로 자동 생성합니다.

외부 의존 스킬 없이 독립적으로 호출 가능합니다.
생성된 리포트는 마크다운 문자열로 반환되며, 에이전트가 이를 그대로 답변에 포함하거나
파일로 저장하는 데 사용할 수 있습니다.

## 실행 흐름

```
[generate-report]  ← 독립 실행 가능 (depends_on: [])
```

## 파라미터

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
| ---------- | ------ | ------ | -------- | ------ |
| report_type | string | Y | — | `daily`, `weekly`, `monthly` 중 하나 |
| date_range | object | Y | — | `{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}` |
| metrics | array | N | (유형별 기본값) | 포함할 지표 코드 목록 |

### report_type 별 기본 지표

| report_type | 기본 포함 지표 |
| ------------- | ---------------- |
| `daily` | `new_contracts`, `premiums_collected`, `claims_submitted`, `claims_paid` |
| `weekly` | 위 4개 + `customer_satisfaction`, `avg_processing_time` |
| `monthly` | 전체 지표 포함 |

### 지원 metrics 코드

| 코드 | 설명 |
| ------ | ------ |
| `new_contracts` | 신규 계약 건수 |
| `premiums_collected` | 보험료 수납 합계 (원) |
| `claims_submitted` | 청구 접수 건수 |
| `claims_paid` | 지급 완료 건수 및 금액 |
| `claims_rejected` | 부지급 건수 및 사유 분류 |
| `customer_satisfaction` | 고객 만족도 평균 점수 (5점 만점) |
| `avg_processing_time` | 청구 평균 처리 기간 (일) |
| `top_products` | 판매 상위 상품 TOP 5 |
| `channel_breakdown` | 채널별(대면/비대면/CM) 계약 비중 |
| `lapse_rate` | 실효/해약률 |

## 응답 형식

```json
{
  "report_id": "RPT-20260319-001",
  "report_type": "daily",
  "date_range": {"start": "2026-03-18", "end": "2026-03-18"},
  "generated_at": "2026-03-19T09:00:00Z",
  "metrics_included": ["new_contracts", "premiums_collected", "claims_submitted", "claims_paid"],
  "content": "# 일간 실적 리포트\n\n**기준일: 2026-03-18**\n\n..."
}
```

`content` 필드에 마크다운 형식의 리포트 전문이 포함됩니다.

### 생성 리포트 구조 예시 (daily)

```markdown
# 일간 실적 리포트

**기준일: 2026-03-18**
**생성일시: 2026-03-19 09:00 KST**

## 신규 계약
| 구분 | 건수 | 전일 대비 |
| ------ | ------ | ----------- |
| 종신보험 | 42 | +5 (▲13.5%) |
| 건강보험 | 87 | -3 (▼3.3%) |
| 연금보험 | 31 | +2 (▲6.9%) |
| **합계** | **160** | **+4 (▲2.6%)** |

## 보험료 수납
- 총 수납액: **482,300,000 원**
- 전일 대비: +12,500,000 원 (▲2.7%)

## 보험금 청구 및 지급
| 항목 | 건수 | 금액 |
| ------ | ------ | ------ |
| 청구 접수 | 23 | — |
| 지급 완료 | 18 | 134,500,000 원 |
| 심사 중 | 5 | — |
```

## 에러 코드

| 코드 | HTTP 상태 | 설명 | 대응 |
| ------ | ----------- | ------ | ------ |
| R001 | 400 | 잘못된 report_type | daily/weekly/monthly 중 하나 사용 |
| R002 | 400 | date_range 형식 오류 | YYYY-MM-DD 형식 및 start <= end 확인 |
| R003 | 400 | 지원하지 않는 metrics 코드 | 지원 코드 목록 참조 |
| R004 | 422 | 조회 기간이 허용 범위 초과 | daily: 최대 31일, weekly: 최대 13주, monthly: 최대 24개월 |
| R005 | 503 | 리포팅 시스템 응답 없음 | 잠시 후 재시도 |
| R006 | 504 | 데이터 집계 시간 초과 | 조회 기간 축소 후 재시도 |

## 사용 예시

```python
# 전일 일간 리포트 (기본 지표)
result = await generate_report_tool.ainvoke({
    "report_type": "daily",
    "date_range": {"start": "2026-03-18", "end": "2026-03-18"}
})

# 이번 달 월간 리포트 — 특정 지표만 선택
result = await generate_report_tool.ainvoke({
    "report_type": "monthly",
    "date_range": {"start": "2026-03-01", "end": "2026-03-31"},
    "metrics": ["new_contracts", "premiums_collected", "lapse_rate", "top_products"]
})

# 지난 주 주간 리포트
result = await generate_report_tool.ainvoke({
    "report_type": "weekly",
    "date_range": {"start": "2026-03-10", "end": "2026-03-16"}
})
```

## 주의 사항

- 당일 데이터는 오전 2시 배치 집계 이후부터 조회 가능하며, 집계 전에는 전일 데이터까지만 반환됩니다.
- `date_range.end` 가 오늘 이후 미래 날짜인 경우 R002 오류가 반환됩니다.
- 대용량 기간(예: monthly 24개월)은 응답에 최대 60초가 소요될 수 있습니다.
- 생성된 리포트의 `report_id` 를 보관하면 `/api/report/{report_id}` 엔드포인트로 재조회할 수 있습니다.
