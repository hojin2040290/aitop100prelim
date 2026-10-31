# 예선 제출 적합성 체크리스트

| 항목 | 상태 | 근거 |
|---|---|---|
| 41개 operation 등록(GET 23 + POST 17 + reset 1), 누락 시 import 실패 | 구현·테스트 | `api_registry.load_operations`, `tests/test_registry.py` |
| 40개 업무 API 각각 요청 조립·스키마 검증 테스트 | 구현·테스트(40건) | `test_every_business_operation_builds` |
| reset 상담 경로 미노출, 관리자 스크립트만 | 구현·테스트 | `test_reset_not_exposed_to_llm`, `test_reset_cannot_be_called_from_agent_path` |
| 쿼리 포함 path key 분리 | 구현·테스트 | `test_query_path_split` |
| additionalProperties:false·enum 위반 사전 차단 | 구현·테스트 | `test_additional_properties_and_enum_rejected` |
| 모든 호출에 TC 헤더, TC 없으면 호출 0 | 구현·테스트 | `test_identify_and_order_ownership`, `_raw` |
| 404 vs [] 구분, 503 재시도, 429 Retry-After·누적 중단 | 구현·일부 테스트 | `test_retry_on_503_then_success_and_404_vs_empty` |
| 동일 대상 재접수(덮어쓰기) 방지 | 구현·테스트 | `test_refund_guard_and_duplicate`, escalate dup |
| 인입 계정 인증 + 주문 귀속, 타인 주문·수령인·주소 비공개 | 구현·테스트 | `test_identify_and_order_ownership`, `test_unverified_blocks_order_actions` |
| 5만원 재량 한도(하자 전액·품목 전액 예외) | 구현·테스트 | `test_refund_guard_and_duplicate` |
| 카드=취소, 현금·이체=현금영수증 | 구현·테스트 | `test_payment_method_guards` |
| 원장에 없는 쿠폰 코드 발급 차단 | 구현·테스트 | `test_coupon_requires_registered_promo_and_own_member` |
| LANE·대상 5종 검증, 회신 기한 3영업일 | 구현·테스트 | `test_escalation_format_and_deadline` |
| 영업일·컷오프·하자 기한·가격 인하·중량·쿠폰 기간 | 구현·테스트 | `tests/test_policy.py` |
| TC 전환 시 세션 초기화(정보 누출 방지) | 구현·테스트 | `test_agent_end_to_end_with_scripted_llm` |
| 웹훅 1초 내 2xx, 이벤트 중복 제거, 콜백 | 구현·테스트 | `tests/test_server.py` |
| SimpleText 1개·500자·마크다운 제거 | 구현·테스트 | `test_long_answer_is_limited` |
| LLM 장애 시 접수번호 보존 폴백 | 구현·테스트 | `test_agent_llm_failure_falls_back_with_receipts` |
| 실제 Action API·실제 Qwen으로 공개 TC 검증 | **미실시** | 이 개발 환경에 토큰·공개 TC ID·GPU 없음 → `scripts/cli_chat.py`로 직접 수행 필요 |
| 카카오 실제 페이로드 필드명·콜백 계약 실측 | **미실시** | 기존 `kakao_bot.py`의 탐색 방식 유지, `/health`·audit로 확인 |
| p95 실측 | **미실시** | GPU 환경에서 `/health` p95_ms 확인 |

## 대회 규정 적용 (AI_TOP_100 [2026] 예선 규정)

| 조항 | 요구 | 구현/조치 | 확인 |
|---|---|---|---|
| 제2조 | 본인 직접 수행, 계정 공유 금지 | 콘솔·토큰은 본인만 사용 | 참가자 |
| 제3조 | 1인 장소·비공용 네트워크 | 운영 준수 | 참가자 |
| 제4조 | 10:00 전 동의·인증 | — | 완료된 사항 |
| 제5조 | **15:00까지 App ID·디브리프 1회 제출**, 이후 변경 금지 | 설정 분리(.env), 제출 커밋 태그 | `docs/OPERATIONS.md` §2 |
| 제6조 | 카카오톡 봇 API 채널 챗봇, 액션 API 연동 필수 | `/kakao/webhook` DISPATCH·콜백, Action API 40개 | `tests/test_server.py`, `tests/test_registry.py` |
| 제7조 | 프롬프트 인젝션 방어 | `security.py`: 입력 2,000자 제한, 템플릿 토큰 제거, 인젝션 탐지·경고, 내부 지침·도구명·토큰 누출 차단, 대화별 분당 8건 제한 + 프롬프트 방어 지침 + 권한 주장 무시 코드 가드 | `tests/test_security.py` |
| 제7조 | 11-01 24:00까지 정상 작동 | 자동 재시작, LLM 폴백, 영속 세션, `/health` llm_alive | GPU 예약 시간 확인 |
| 제8조 | 환경 장애 비보상 | 폴백 답변(접수번호 보존), 재기동 절차 | `docs/OPERATIONS.md` §4 |
| 제9조 | 시스템 공격·대량 요청 금지 | Action API 95/60s 제한, 누적 3,000 감시, 심사 중 수동 호출 금지 | `action_client.py` |
| 제10조 | 문의는 aitop100@kakaoimpact.org | — | 참가자 |
