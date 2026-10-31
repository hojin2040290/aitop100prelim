# Action API 완전 명세 인벤토리

출처: `original_sources/actions.json` (OpenAPI 3.1). 아래는 자동 파싱한 개요이며, **원문 JSON이 필드·허용값의 유일한 계약**이다.

**계수 검증: 조회 GET 23개, 업무 접수 POST 17개, 연습 데이터 초기화 POST 1개 = 총 41개.**

## 공통 인증·실패·접수 동작

- 기본 URL: `https://gyodong-mall-action.aitop100.org`
- 헤더: `Authorization: Bearer <ACTION_TOKEN>` 및 `X-Aitop100-Test-Case-Id: <TC_ID>`
- 요청·응답 JSON은 원문 스키마를 따르고 `additionalProperties:false`를 준수한다.
- 같은 TC ID 유지; 공개 TC만 사전 연습; 데이터는 여러 TC에서 공유됨.
- 누적 평가 3,000회, 분당 100회; 본문 없는 400/404도 카운트.
- GET 단건 404, 검색 200 `[]`; 404는 잘못된 URL일 수도 있음.
- 접수 POST는 상태·잔액을 바꾸지 않고 접수번호만 기록한다. 정책 위반도 서버에서 거부하지 않을 수 있음.
- 동일 대상 접수 재호출 시 같은 접수번호와 마지막 본문이 남으므로 중복 실행 금지.
- `429` 일시 제한은 `Retry-After` 이용, 누적 소진은 재시도로 해결 안 됨.

## 전체 Operation 목록

| ID | 메서드 | 경로 | 기능 | 요청 body 필수값 |
|---|---|---|---|---|
| API-01 | GET | `/api/products/{sku}` | 상품 조회 | 없음 |
| API-02 | GET | `/api/products` | 품목별 상품 검색 | 없음 |
| API-03 | GET | `/api/lots/{lot_id}` | 로트 조회 | 없음 |
| API-04 | GET | `/api/lots/{lot_id}/investigation` | 로트 조사 조회 | 없음 |
| API-05 | GET | `/api/tickets` | 회원별 상담 이력 검색 | 없음 |
| API-06 | GET | `/api/tickets` | 로트별 상담 이력 검색 | 없음 |
| API-07 | GET | `/api/orders/{order_no}` | 주문 조회 | 없음 |
| API-08 | GET | `/api/orders` | 회원별 주문 검색 | 없음 |
| API-09 | GET | `/api/orders` | 유입태그별 주문 검색 | 없음 |
| API-10 | GET | `/api/shipments/{shipment_id}` | 배송 조회 | 없음 |
| API-11 | GET | `/api/shipments` | 주문별 배송 검색 | 없음 |
| API-12 | GET | `/api/members/{member_id}` | 조합원 조회 | 없음 |
| API-13 | GET | `/api/members` | 이름 조합원 검색 | 없음 |
| API-14 | GET | `/api/members` | 추천인별 조합원 검색 | 없음 |
| API-15 | GET | `/api/point-entries` | 적립금 내역 검색 | 없음 |
| API-16 | GET | `/api/coupons` | 회원별 쿠폰 검색 | 없음 |
| API-17 | GET | `/api/payments/{approval_no}` | 결제 조회 | 없음 |
| API-18 | GET | `/api/payments` | 주문별 결제 검색 | 없음 |
| API-19 | GET | `/api/subscriptions/{subscription_id}` | 구독 조회 | 없음 |
| API-20 | GET | `/api/promos/{code}` | 프로모션 조회 | 없음 |
| API-21 | GET | `/api/inventory` | 재고 조회 | 없음 |
| API-22 | POST | `/api/orders/{order_no}/restore-requests` | 주문 복구 접수 | 없음 |
| API-23 | POST | `/api/orders/{order_no}/change-requests` | 주문 변경 접수 | `requested_items` |
| API-24 | POST | `/api/orders/{order_no}/address-change-requests` | 배송지 변경 접수 | `new_address` |
| API-25 | POST | `/api/orders/{order_no}/schedule-change-requests` | 배송 일정 변경 접수 | `requested_date` |
| API-26 | POST | `/api/orders/{order_no}/memos` | 주문 메모 접수 | `memo` |
| API-27 | POST | `/api/orders/{order_no}/expedite-requests` | 긴급 출고 접수 | `qty`, `reason` |
| API-28 | POST | `/api/shipments/{shipment_id}/reship-requests` | 재배송 접수 | 없음 |
| API-29 | POST | `/api/refunds` | 환불 신청 | `order_no`, `amount`, `reason` |
| API-30 | GET | `/api/refunds` | 주문별 환불 검색 | 없음 |
| API-31 | POST | `/api/payments/{approval_no}/cancellation-requests` | 카드 취소 접수 | 없음 |
| API-32 | POST | `/api/payments/{approval_no}/cash-receipt-requests` | 현금영수증 발행 접수 | `receipt_number` |
| API-33 | POST | `/api/members/{member_id}/coupon-issue-requests` | 쿠폰 발급 접수 | `promo_code` |
| API-34 | POST | `/api/members/{member_id}/reward-requests` | 리워드 지급 접수 | 없음 |
| API-35 | POST | `/api/escalations` | 에스컬레이션 | `lane`, `reason` |
| API-36 | GET | `/api/escalations/{escalation_id}` | 에스컬레이션 조회 | 없음 |
| API-37 | POST | `/api/shipments/{shipment_id}/reship-charge-requests` | 재배송비 청구 접수 | `charge_amount` |
| API-38 | POST | `/api/orders/{order_no}/pickup-requests` | 픽업 접수 | `qty`, `trigger`, `cost_bearer` |
| API-39 | POST | `/api/products/{sku}/restock-notification-requests` | 재입고 알림 등록 | 없음 |
| API-40 | POST | `/api/subscriptions/{subscription_id}/change-requests` | 구독 변경 접수 | `kind` |
| resetMyActionData | POST | `/api/action-data/reset` | 내 액션 데이터 전체 초기화 | 없음 |

## API별 상세 요청 필드 및 응답 데이터 계약

### API-01 GET /api/products/{sku} — 상품 조회

- 분류: 상품·로트·재고
- 파라미터: `sku` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-02 GET /api/products?item= — 품목별 상품 검색

- 분류: 상품·로트·재고
- 파라미터: `item` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-03 GET /api/lots/{lot_id} — 로트 조회

- 분류: 상품·로트·재고
- 파라미터: `lot_id` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-04 GET /api/lots/{lot_id}/investigation — 로트 조사 조회

- 분류: 상품·로트·재고
- 파라미터: `lot_id` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-05 GET /api/tickets?member_id= — 회원별 상담 이력 검색

- 분류: 조합원
- 파라미터: `member_id` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-06 GET /api/tickets?lot_id= — 로트별 상담 이력 검색

- 분류: 조합원
- 파라미터: `lot_id` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-07 GET /api/orders/{order_no} — 주문 조회

- 분류: 주문
- 파라미터: `order_no` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-08 GET /api/orders?member_id= — 회원별 주문 검색

- 분류: 주문
- 파라미터: `member_id` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-09 GET /api/orders?inflow_tag= — 유입태그별 주문 검색

- 분류: 주문
- 파라미터: `inflow_tag` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-10 GET /api/shipments/{shipment_id} — 배송 조회

- 분류: 배송·구독
- 파라미터: `shipment_id` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-11 GET /api/shipments?order_no= — 주문별 배송 검색

- 분류: 배송·구독
- 파라미터: `order_no` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-12 GET /api/members/{member_id} — 조합원 조회

- 분류: 조합원
- 파라미터: `member_id` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-13 GET /api/members?name= — 이름 조합원 검색

- 분류: 조합원
- 파라미터: `name` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-14 GET /api/members?referred_by= — 추천인별 조합원 검색

- 분류: 조합원
- 파라미터: `referred_by` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-15 GET /api/point-entries?member_id= — 적립금 내역 검색

- 분류: 조합원
- 파라미터: `member_id` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-16 GET /api/coupons?member_id= — 회원별 쿠폰 검색

- 분류: 프로모션·쿠폰
- 파라미터: `member_id` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-17 GET /api/payments/{approval_no} — 결제 조회

- 분류: 결제·환불
- 파라미터: `approval_no` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-18 GET /api/payments?order_no= — 주문별 결제 검색

- 분류: 결제·환불
- 파라미터: `order_no` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-19 GET /api/subscriptions/{subscription_id} — 구독 조회

- 분류: 배송·구독
- 파라미터: `subscription_id` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-20 GET /api/promos/{code} — 프로모션 조회

- 분류: 프로모션·쿠폰
- 파라미터: `code` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-21 GET /api/inventory?sku= — 재고 조회

- 분류: 상품·로트·재고
- 파라미터: `sku` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-22 POST /api/orders/{order_no}/restore-requests — 주문 복구 접수

- 분류: 주문
- 파라미터: `order_no` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-23 POST /api/orders/{order_no}/change-requests — 주문 변경 접수

- 분류: 주문
- 파라미터: `order_no` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "requested_items": {
      "type": "array",
      "description": "변경할 품목마다 SKU와 수량을 문자열 하나로 적습니다. 표기 형식은 자유입니다.",
      "items": {
        "type": "string"
      }
    }
  },
  "required": [
    "requested_items"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-24 POST /api/orders/{order_no}/address-change-requests — 배송지 변경 접수

- 분류: 배송·구독
- 파라미터: `order_no` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "new_address": {
      "type": "string"
    }
  },
  "required": [
    "new_address"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-25 POST /api/orders/{order_no}/schedule-change-requests — 배송 일정 변경 접수

- 분류: 배송·구독
- 파라미터: `order_no` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "requested_date": {
      "type": "string",
      "format": "date"
    }
  },
  "required": [
    "requested_date"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-26 POST /api/orders/{order_no}/memos — 주문 메모 접수

- 분류: 주문
- 파라미터: `order_no` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "memo": {
      "type": "string"
    }
  },
  "required": [
    "memo"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-27 POST /api/orders/{order_no}/expedite-requests — 긴급 출고 접수

- 분류: 배송·구독
- 파라미터: `order_no` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "qty": {
      "type": "integer",
      "format": "int32"
    },
    "reason": {
      "type": "string"
    }
  },
  "required": [
    "qty",
    "reason"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-28 POST /api/shipments/{shipment_id}/reship-requests — 재배송 접수

- 분류: 배송·구독
- 파라미터: `shipment_id` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-29 POST /api/refunds — 환불 신청

- 분류: 결제·환불
- 경로/쿼리 입력 없음 (공통 TC 헤더 필요).
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "order_no": {
      "type": "string"
    },
    "amount": {
      "type": "integer",
      "format": "int32"
    },
    "reason": {
      "type": "string"
    }
  },
  "required": [
    "order_no",
    "amount",
    "reason"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-30 GET /api/refunds?order_no= — 주문별 환불 검색

- 분류: 결제·환불
- 파라미터: `order_no` (query, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-31 POST /api/payments/{approval_no}/cancellation-requests — 카드 취소 접수

- 분류: 결제·환불
- 파라미터: `approval_no` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-32 POST /api/payments/{approval_no}/cash-receipt-requests — 현금영수증 발행 접수

- 분류: 결제·환불
- 파라미터: `approval_no` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "receipt_number": {
      "type": "string"
    }
  },
  "required": [
    "receipt_number"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-33 POST /api/members/{member_id}/coupon-issue-requests — 쿠폰 발급 접수

- 분류: 프로모션·쿠폰
- 파라미터: `member_id` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "promo_code": {
      "type": "string"
    }
  },
  "required": [
    "promo_code"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-34 POST /api/members/{member_id}/reward-requests — 리워드 지급 접수

- 분류: 조합원
- 파라미터: `member_id` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-35 POST /api/escalations — 에스컬레이션

- 분류: 에스컬레이션
- 경로/쿼리 입력 없음 (공통 TC 헤더 필요).
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "lane": {
      "type": "string"
    },
    "reason": {
      "type": "string"
    }
  },
  "required": [
    "lane",
    "reason"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `429`, `500`, `503`

### API-36 GET /api/escalations/{escalation_id} — 에스컬레이션 조회

- 분류: 에스컬레이션
- 파라미터: `escalation_id` (path, 필수, `string`)
- 조회이며 응답 shape는 `actions.json` Responses `$ref`를 따른다.
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-37 POST /api/shipments/{shipment_id}/reship-charge-requests — 재배송비 청구 접수

- 분류: 배송·구독
- 파라미터: `shipment_id` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "charge_amount": {
      "type": "integer",
      "format": "int32"
    }
  },
  "required": [
    "charge_amount"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-38 POST /api/orders/{order_no}/pickup-requests — 픽업 접수

- 분류: 배송·구독
- 파라미터: `order_no` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "qty": {
      "type": "integer",
      "format": "int32"
    },
    "trigger": {
      "type": "string"
    },
    "cost_bearer": {
      "type": "string",
      "enum": [
        "SELLER",
        "CUSTOMER"
      ]
    }
  },
  "required": [
    "qty",
    "trigger",
    "cost_bearer"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-39 POST /api/products/{sku}/restock-notification-requests — 재입고 알림 등록

- 분류: 상품·로트·재고
- 파라미터: `sku` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### API-40 POST /api/subscriptions/{subscription_id}/change-requests — 구독 변경 접수

- 분류: 배송·구독
- 파라미터: `subscription_id` (path, 필수, `string`)
- 요청 JSON Schema:
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "kind": {
      "type": "string",
      "enum": [
        "SKIP",
        "CANCEL"
      ]
    }
  },
  "required": [
    "kind"
  ]
}
```
- 응답 코드: `200`, `400`, `401`, `403`, `404`, `429`, `500`, `503`

### resetMyActionData POST /api/action-data/reset — 내 액션 데이터 전체 초기화

- 분류: 내 데이터
- 경로/쿼리 입력 없음 (공통 TC 헤더 필요).
- 요청 JSON Schema:
```json
{}
```
- 응답 코드: `204`, `401`, `403`, `409`, `429`, `500`, `503`

## 전체 Components Schemas 원문 (개발 시 타입 생성 기준)

### Error
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "code": {
      "type": "string",
      "description": "오류 코드"
    },
    "message": {
      "type": "string",
      "description": "오류 메시지"
    }
  },
  "required": [
    "code",
    "message"
  ]
}
```

### OrderRestoreRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "order_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at"
  ]
}
```

### OrderChangeRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "order_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at"
  ]
}
```

### AddressChangeRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "order_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at"
  ]
}
```

### ScheduleChangeRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "order_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at"
  ]
}
```

### OrderMemosReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "memo_id": {
      "type": "string",
      "description": "접수번호"
    },
    "order_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "memo_id",
    "order_no",
    "request_status",
    "requested_at"
  ]
}
```

### ExpediteRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "order_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at"
  ]
}
```

### ReshipRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "shipment_id": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "shipment_id",
    "request_status",
    "requested_at"
  ]
}
```

### RefundsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "refund_id": {
      "type": "string",
      "description": "접수번호"
    },
    "order_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "refund_id",
    "order_no",
    "request_status",
    "requested_at"
  ]
}
```

### PaymentCancellationRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "approval_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "approval_no",
    "request_status",
    "requested_at"
  ]
}
```

### CashReceiptRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "approval_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "approval_no",
    "request_status",
    "requested_at"
  ]
}
```

### CouponIssueRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "member_id": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "member_id",
    "request_status",
    "requested_at"
  ]
}
```

### RewardRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "member_id": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "member_id",
    "request_status",
    "requested_at"
  ]
}
```

### EscalationsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "escalation_id": {
      "type": "string",
      "description": "접수번호"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "escalation_id",
    "request_status",
    "requested_at"
  ]
}
```

### ReshipChargeRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "shipment_id": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "shipment_id",
    "request_status",
    "requested_at"
  ]
}
```

### PickupRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "order_no": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at"
  ]
}
```

### RestockNotificationRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "sku": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "sku",
    "request_status",
    "requested_at"
  ]
}
```

### SubscriptionChangeRequestsReceipt
```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "요청 접수 결과",
  "properties": {
    "request_id": {
      "type": "string",
      "description": "접수번호"
    },
    "subscription_id": {
      "type": "string",
      "description": "접수 대상 식별자"
    },
    "request_status": {
      "type": "string",
      "description": "접수 상태",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time",
      "description": "접수 시각"
    }
  },
  "required": [
    "request_id",
    "subscription_id",
    "request_status",
    "requested_at"
  ]
}
```

### AddressChangeRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "order_no": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "new_address": {
      "type": "string"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at",
    "new_address"
  ]
}
```

### CashReceiptRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "approval_no": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "receipt_number": {
      "type": "string"
    }
  },
  "required": [
    "request_id",
    "approval_no",
    "request_status",
    "requested_at",
    "receipt_number"
  ]
}
```

### CouponIssueRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "member_id": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "promo_code": {
      "type": "string"
    }
  },
  "required": [
    "request_id",
    "member_id",
    "request_status",
    "requested_at",
    "promo_code"
  ]
}
```

### Coupons
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "coupon_id": {
      "type": "string"
    },
    "member_id": {
      "type": "string"
    },
    "promo_code": {
      "type": "string"
    },
    "issued_at": {
      "type": "string",
      "format": "date-time"
    },
    "expires_at": {
      "type": "string",
      "format": "date"
    },
    "used_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date-time"
    }
  },
  "required": [
    "coupon_id",
    "member_id",
    "promo_code",
    "issued_at",
    "expires_at",
    "used_at"
  ]
}
```

### Escalations
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "escalation_id": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "lane": {
      "type": "string"
    },
    "reason": {
      "type": "string"
    },
    "status": {
      "type": "string",
      "enum": [
        "APPROVED",
        "REJECTED",
        "PENDING"
      ]
    }
  },
  "required": [
    "escalation_id",
    "request_status",
    "requested_at",
    "lane",
    "reason",
    "status"
  ]
}
```

### ExpediteRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "order_no": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "qty": {
      "type": "integer"
    },
    "reason": {
      "type": "string"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at",
    "qty",
    "reason"
  ]
}
```

### Inventory
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "sku": {
      "type": "string"
    },
    "total_qty": {
      "type": "integer"
    },
    "sale_state": {
      "type": "string",
      "enum": [
        "ON_SALE",
        "PREORDER",
        "SOLD_OUT",
        "CLOSED"
      ]
    }
  },
  "required": [
    "sku",
    "total_qty",
    "sale_state"
  ]
}
```

### LotInvestigations
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "lot_id": {
      "type": "string"
    },
    "status": {
      "type": "string",
      "enum": [
        "IN_PROGRESS",
        "CLOSED"
      ]
    },
    "symptom": {
      "type": "string",
      "enum": [
        "BLACK_HEART",
        "MOLD"
      ]
    },
    "liability": {
      "type": [
        "string",
        "null"
      ],
      "enum": [
        "DISTRIBUTION",
        "PRODUCTION",
        "CARRIER",
        null
      ]
    },
    "finding": {
      "type": [
        "string",
        "null"
      ]
    },
    "disclosure_approved": {
      "type": [
        "boolean",
        "null"
      ]
    },
    "opened_at": {
      "type": "string",
      "format": "date-time"
    },
    "closed_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date-time"
    }
  },
  "required": [
    "lot_id",
    "status",
    "symptom",
    "liability",
    "finding",
    "disclosure_approved",
    "opened_at",
    "closed_at"
  ]
}
```

### Lots
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "lot_id": {
      "type": "string"
    },
    "sku": {
      "type": "string"
    },
    "packed_at": {
      "type": "string",
      "format": "date-time"
    },
    "measured_weight_g": {
      "type": "integer"
    },
    "measured_brix": {
      "type": [
        "number",
        "null"
      ]
    },
    "grade": {
      "type": "string",
      "enum": [
        "PREMIUM",
        "STANDARD",
        "FAIR",
        "IMPERFECT",
        "REJECT"
      ]
    },
    "qty_in_stock": {
      "type": "integer"
    },
    "status": {
      "type": "string",
      "enum": [
        "ACTIVE",
        "HOLD",
        "DISPOSED"
      ]
    },
    "sprayed_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date"
    }
  },
  "required": [
    "lot_id",
    "sku",
    "packed_at",
    "measured_weight_g",
    "measured_brix",
    "grade",
    "qty_in_stock",
    "status",
    "sprayed_at"
  ]
}
```

### Members
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "member_id": {
      "type": "string"
    },
    "name": {
      "type": "string"
    },
    "phone": {
      "type": "string"
    },
    "birth_year": {
      "type": "integer"
    },
    "member_type": {
      "type": "string",
      "enum": [
        "INDIVIDUAL",
        "BUSINESS",
        "GROUP_BUY_OPERATOR"
      ]
    },
    "grade": {
      "type": "string",
      "enum": [
        "MEMBER",
        "REGULAR"
      ]
    },
    "status": {
      "type": "string",
      "enum": [
        "ACTIVE",
        "WITHDRAWAL_REQUESTED",
        "WITHDRAWN"
      ]
    },
    "address": {
      "type": [
        "string",
        "null"
      ]
    },
    "joined_at": {
      "type": "string",
      "format": "date"
    },
    "referred_by_member_id": {
      "type": [
        "string",
        "null"
      ]
    }
  },
  "required": [
    "member_id",
    "name",
    "phone",
    "birth_year",
    "member_type",
    "grade",
    "status",
    "address",
    "joined_at",
    "referred_by_member_id"
  ]
}
```

### OrderChangeRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "order_no": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "requested_items": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at",
    "requested_items"
  ]
}
```

### OrderItems
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "order_no": {
      "type": "string"
    },
    "sku": {
      "type": "string"
    },
    "name": {
      "type": "string"
    },
    "qty": {
      "type": "integer"
    },
    "unit_price": {
      "type": "integer"
    }
  },
  "required": [
    "order_no",
    "sku",
    "name",
    "qty",
    "unit_price"
  ]
}
```

### OrderMemos
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "memo_id": {
      "type": "string"
    },
    "order_no": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "memo": {
      "type": "string"
    }
  },
  "required": [
    "memo_id",
    "order_no",
    "request_status",
    "requested_at",
    "memo"
  ]
}
```

### OrderRestoreRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "order_no": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at"
  ]
}
```

### Orders
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "order_no": {
      "type": "string"
    },
    "member_id": {
      "type": "string"
    },
    "status": {
      "type": "string",
      "enum": [
        "PAID",
        "CONFIRMED",
        "CANCEL_REQUESTED",
        "CANCELED",
        "FAILED"
      ]
    },
    "status_changed_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date-time"
    },
    "ordered_at": {
      "type": "string",
      "format": "date-time"
    },
    "amount": {
      "type": "integer"
    },
    "recipient_name": {
      "type": "string"
    },
    "shipping_address": {
      "type": "string"
    },
    "inflow_tag": {
      "type": [
        "string",
        "null"
      ]
    },
    "ship_scheduled_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date"
    },
    "failure_code": {
      "type": [
        "string",
        "null"
      ]
    },
    "payment_refs": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "refund_ids": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "change_request_ids": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "sku": {
            "type": "string"
          },
          "name": {
            "type": "string"
          },
          "qty": {
            "type": "integer"
          },
          "unit_price": {
            "type": "integer"
          }
        },
        "required": [
          "sku",
          "name",
          "qty",
          "unit_price"
        ]
      }
    }
  },
  "required": [
    "order_no",
    "member_id",
    "status",
    "status_changed_at",
    "ordered_at",
    "amount",
    "recipient_name",
    "shipping_address",
    "inflow_tag",
    "ship_scheduled_at",
    "failure_code",
    "payment_refs",
    "refund_ids",
    "change_request_ids",
    "items"
  ]
}
```

### PaymentCancellationRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "approval_no": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": [
    "request_id",
    "approval_no",
    "request_status",
    "requested_at"
  ]
}
```

### Payments
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "approval_no": {
      "type": "string"
    },
    "order_no": {
      "type": [
        "string",
        "null"
      ]
    },
    "pay_method": {
      "type": "string"
    },
    "amount": {
      "type": "integer"
    },
    "paid_at": {
      "type": "string",
      "format": "date-time"
    },
    "status": {
      "type": "string",
      "enum": [
        "APPROVED",
        "CANCELED"
      ]
    },
    "payer_name": {
      "type": [
        "string",
        "null"
      ]
    },
    "cancellation_request_ids": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "card_last4": {
      "type": [
        "string",
        "null"
      ]
    }
  },
  "required": [
    "approval_no",
    "order_no",
    "pay_method",
    "amount",
    "paid_at",
    "status",
    "payer_name",
    "cancellation_request_ids",
    "card_last4"
  ]
}
```

### PickupRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "order_no": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "qty": {
      "type": "integer"
    },
    "trigger": {
      "type": "string"
    },
    "cost_bearer": {
      "type": "string",
      "enum": [
        "SELLER",
        "CUSTOMER"
      ]
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at",
    "qty",
    "trigger",
    "cost_bearer"
  ]
}
```

### PointEntries
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "entry_id": {
      "type": "string"
    },
    "member_id": {
      "type": "string"
    },
    "amount": {
      "type": "integer"
    },
    "granted_at": {
      "type": "string",
      "format": "date"
    },
    "expires_at": {
      "type": "string",
      "format": "date"
    }
  },
  "required": [
    "entry_id",
    "member_id",
    "amount",
    "granted_at",
    "expires_at"
  ]
}
```

### Products
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "sku": {
      "type": "string"
    },
    "name": {
      "type": "string"
    },
    "origin": {
      "type": "string"
    },
    "variety": {
      "type": [
        "string",
        "null"
      ]
    },
    "listed_weight": {
      "type": "string"
    },
    "grade": {
      "type": [
        "array",
        "null"
      ],
      "items": {
        "type": "string",
        "enum": [
          "PREMIUM",
          "STANDARD",
          "FAIR",
          "IMPERFECT",
          "REJECT"
        ]
      }
    },
    "price": {
      "type": "integer"
    },
    "sale_state": {
      "type": "string",
      "enum": [
        "ON_SALE",
        "PREORDER",
        "SOLD_OUT",
        "CLOSED"
      ]
    }
  },
  "required": [
    "sku",
    "name",
    "origin",
    "variety",
    "listed_weight",
    "grade",
    "price",
    "sale_state"
  ]
}
```

### Promotions
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "code": {
      "type": "string"
    },
    "name": {
      "type": "string"
    },
    "benefit_type": {
      "type": "string",
      "enum": [
        "RATE",
        "AMOUNT"
      ]
    },
    "benefit_value": {
      "type": "integer"
    },
    "valid_from": {
      "type": "string",
      "format": "date"
    },
    "valid_until": {
      "type": [
        "string",
        "null"
      ],
      "format": "date"
    },
    "target_skus": {
      "type": [
        "array",
        "null"
      ],
      "items": {
        "type": "string"
      }
    },
    "stackable_with": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": [
          "DISCOUNT_CODE",
          "REWARD_COUPON",
          "POINTS"
        ]
      }
    }
  },
  "required": [
    "code",
    "name",
    "benefit_type",
    "benefit_value",
    "valid_from",
    "valid_until",
    "target_skus",
    "stackable_with"
  ]
}
```

### Refunds
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "refund_id": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "order_no": {
      "type": "string"
    },
    "amount": {
      "type": "integer"
    },
    "reason": {
      "type": "string"
    }
  },
  "required": [
    "refund_id",
    "request_status",
    "requested_at",
    "order_no",
    "amount",
    "reason"
  ]
}
```

### ReshipChargeRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "shipment_id": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "charge_amount": {
      "type": "integer"
    }
  },
  "required": [
    "request_id",
    "shipment_id",
    "request_status",
    "requested_at",
    "charge_amount"
  ]
}
```

### ReshipRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "shipment_id": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": [
    "request_id",
    "shipment_id",
    "request_status",
    "requested_at"
  ]
}
```

### RestockNotificationRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "sku": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": [
    "request_id",
    "sku",
    "request_status",
    "requested_at"
  ]
}
```

### RewardRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "member_id": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": [
    "request_id",
    "member_id",
    "request_status",
    "requested_at"
  ]
}
```

### ScheduleChangeRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "order_no": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "requested_date": {
      "type": "string",
      "format": "date"
    }
  },
  "required": [
    "request_id",
    "order_no",
    "request_status",
    "requested_at",
    "requested_date"
  ]
}
```

### ShipmentItems
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "shipment_id": {
      "type": "string"
    },
    "sku": {
      "type": "string"
    },
    "qty": {
      "type": "integer"
    },
    "lot_id": {
      "type": "string"
    }
  },
  "required": [
    "shipment_id",
    "sku",
    "qty",
    "lot_id"
  ]
}
```

### Shipments
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "shipment_id": {
      "type": "string"
    },
    "order_no": {
      "type": "string"
    },
    "status": {
      "type": "string",
      "enum": [
        "READY",
        "IN_TRANSIT",
        "DELIVERED",
        "RETURNED"
      ]
    },
    "carrier": {
      "type": "string"
    },
    "invoice_no": {
      "type": "string"
    },
    "picked_up_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date-time"
    },
    "delivered_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date-time"
    },
    "delivered_location": {
      "type": [
        "string",
        "null"
      ]
    },
    "return_reason": {
      "type": [
        "string",
        "null"
      ]
    },
    "item_condition": {
      "type": [
        "string",
        "null"
      ]
    },
    "ship_notice_sent_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date-time"
    },
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "sku": {
            "type": "string"
          },
          "qty": {
            "type": "integer"
          },
          "lot_id": {
            "type": "string"
          }
        },
        "required": [
          "sku",
          "qty",
          "lot_id"
        ]
      }
    }
  },
  "required": [
    "shipment_id",
    "order_no",
    "status",
    "carrier",
    "invoice_no",
    "picked_up_at",
    "delivered_at",
    "delivered_location",
    "return_reason",
    "item_condition",
    "ship_notice_sent_at",
    "items"
  ]
}
```

### SubscriptionChangeRequests
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "type": "string"
    },
    "subscription_id": {
      "type": "string"
    },
    "request_status": {
      "type": "string",
      "enum": [
        "SUBMITTED"
      ]
    },
    "requested_at": {
      "type": "string",
      "format": "date-time"
    },
    "kind": {
      "type": "string",
      "enum": [
        "SKIP",
        "CANCEL"
      ]
    }
  },
  "required": [
    "request_id",
    "subscription_id",
    "request_status",
    "requested_at",
    "kind"
  ]
}
```

### Subscriptions
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "subscription_id": {
      "type": "string"
    },
    "member_id": {
      "type": "string"
    },
    "sku": {
      "type": "string"
    },
    "status": {
      "type": "string",
      "enum": [
        "ACTIVE",
        "CANCELED"
      ]
    },
    "interval": {
      "type": "string"
    },
    "started_at": {
      "type": "string",
      "format": "date"
    }
  },
  "required": [
    "subscription_id",
    "member_id",
    "sku",
    "status",
    "interval",
    "started_at"
  ]
}
```

### Tickets
```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "ticket_id": {
      "type": "string"
    },
    "member_id": {
      "type": "string"
    },
    "lot_id": {
      "type": [
        "string",
        "null"
      ]
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "content": {
      "type": "string"
    },
    "handler": {
      "type": "string"
    }
  },
  "required": [
    "ticket_id",
    "member_id",
    "lot_id",
    "created_at",
    "content",
    "handler"
  ]
}
```
