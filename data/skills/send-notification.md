---
created_at: '2026-03-19T09:00:00Z'
depends_on:
- validate-customer-info
description: 알림 발송 - 고객에게 SMS/카카오톡/이메일 알림을 발송합니다.
endpoint: http://legacy-notification:8080/api/notify/send
method: POST
owner: admin01
inputs:
  customer_id:
    type: string
    description: "고객 번호"
    label: "고객번호"
  channel:
    type: string
    description: "발송 채널"
    label: "발송 채널"
  template_code:
    type: string
    description: "템플릿 코드"
    label: "템플릿 코드"
outputs:
  sent:
    type: boolean
    description: "발송 성공 여부"
  message_id:
    type: string
    description: "메시지 ID"
params:
  channel:
    description: 발송 채널 (sms, kakao, email)
    required: true
    type: string
  customer_id:
    description: 고객 번호
    required: true
    type: string
  template_code:
    description: 알림 템플릿 코드
    required: true
    type: string
  variables:
    description: 템플릿 변수 (key-value 쌍)
    required: false
    type: object
skill_name: send-notification
display_name: "알림 발송"
type: skill
updated_at: '2026-03-19T09:00:00Z'
---

# 알림 발송 (Send Notification)

## 개요

레거시 알림 시스템(legacy-notification)을 통해 고객에게 SMS, 카카오톡 알림톡,
이메일 중 하나의 채널로 메시지를 발송합니다.

고객 정보 유효성 검증이 선행되어야 하므로 `validate-customer-info` 에 의존합니다.
템플릿 코드와 채널을 분리하여 동일한 내용을 여러 채널로 발송하는 경우
각 채널별로 개별 호출이 필요합니다.

## 실행 흐름

```
[validate-customer-info] → [send-notification]
```

## 파라미터

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
| ---------- | ------ | ------ | -------- | ------ |
| customer_id | string | Y | — | 알림을 수신할 고객 번호 |
| channel | string | Y | — | 발송 채널: `sms`, `kakao`, `email` 중 하나 |
| template_code | string | Y | — | 사전 등록된 알림 템플릿 코드 |
| variables | object | N | {} | 템플릿 내 치환 변수. 예: `{"name": "홍길동", "amount": "100,000"}` |

### 지원 채널

| channel 값 | 설명 | 필요 고객 정보 |
| ------------ | ------ | ---------------- |
| `sms` | 단문 문자 메시지 (90자 이내) | 휴대폰 번호 |
| `kakao` | 카카오톡 알림톡 (비즈메시지) | 카카오 연결 휴대폰 번호 |
| `email` | 이메일 | 이메일 주소 |

## 응답 형식

```json
{
  "message_id": "MSG-20260319-000456",
  "customer_id": "CUST-001234",
  "channel": "kakao",
  "template_code": "PREM_CALC_COMPLETE",
  "status": "SENT",
  "sent_at": "2026-03-19T10:05:00Z",
  "recipient": "010-****-5678"
}
```

### 발송 상태 코드

| status | 설명 |
| -------- | ------ |
| SENT | 발송 요청 성공 (최종 수신 여부는 별도 확인) |
| QUEUED | 발송 대기 중 (야간 발송 제한 등) |
| FAILED | 발송 실패 — `error_code` 필드 함께 반환 |

## 템플릿 코드 예시

| template_code | 채널 | 설명 |
| --------------- | ------ | ------ |
| `PREM_CALC_COMPLETE` | sms, kakao | 보험료 산출 완료 안내 |
| `CLAIM_RECEIVED` | sms, kakao, email | 보험금 청구 접수 확인 |
| `CLAIM_APPROVED` | sms, kakao, email | 보험금 지급 승인 안내 |
| `DOC_REQUESTED` | sms, kakao | 추가 서류 제출 요청 |
| `CONTRACT_EXPIRY` | email | 계약 만기 안내 |

## 에러 코드

| 코드 | HTTP 상태 | 설명 | 대응 |
| ------ | ----------- | ------ | ------ |
| N001 | 404 | 고객번호 미존재 | validate-customer-info 선행 호출 확인 |
| N002 | 400 | 지원하지 않는 채널 | channel 값 확인 (sms/kakao/email) |
| N003 | 404 | 템플릿 코드 미존재 | 등록된 template_code 목록 확인 |
| N004 | 422 | 필수 템플릿 변수 누락 | variables 딕셔너리의 키 확인 |
| N005 | 403 | 고객 수신 거부 상태 | 수신 동의 재획득 후 재요청 |
| N006 | 503 | 알림 게이트웨이 응답 없음 | 잠시 후 재시도 |

## 사용 예시

```python
# 카카오톡으로 보험료 산출 완료 알림 발송
result = await send_notification_tool.ainvoke({
    "customer_id": "CUST-001234",
    "channel": "kakao",
    "template_code": "PREM_CALC_COMPLETE",
    "variables": {
        "name": "홍길동",
        "product": "무배당 종신보험",
        "premium": "150,000",
        "currency": "원"
    }
})

# SMS 로 서류 요청 알림
result = await send_notification_tool.ainvoke({
    "customer_id": "CUST-001234",
    "channel": "sms",
    "template_code": "DOC_REQUESTED",
    "variables": {"doc_name": "진단서 원본"}
})
```

## 주의 사항

- 오후 9시 ~ 오전 8시 사이의 발송 요청은 `QUEUED` 상태로 처리되며 다음날 오전 8시 이후 자동 발송됩니다.
- 동일 고객에게 동일 템플릿을 5분 이내에 재발송하면 N007(중복 발송 방지) 오류가 반환됩니다.
- `variables` 의 값은 모두 문자열로 전달해야 합니다. 숫자 타입은 서버에서 자동 변환되지 않습니다.
- `validate-customer-info` 가 선행 호출되지 않으면 N001 오류가 발생할 수 있습니다.
