# 운영 가이드

## 1. 기동 순서

1. GPU 서버에서 LLM: `bash scripts/start_llm.sh` (기존 `reference/legacy/serve.sh`를 쓴다면 `--enable-auto-tool-choice --tool-call-parser hermes --enable-prefix-caching` 추가).
   - 옵션 없이 떠 있으면 에이전트가 400 응답을 감지해 프롬프트 방식 도구 호출로 자동 전환한다(정확도는 네이티브 방식이 낫다).
2. 상담 서버: `bash scripts/run_server.sh` — 프로세스가 죽으면 3초 뒤 재시작, `data/restarts.log` 기록.
3. 터널: `bash reference/legacy/start_tunnel.sh` → 카카오 디벨로퍼스 웹훅 URL `https://<주소>/kakao/webhook`.
4. 확인: `curl -s http://127.0.0.1:9000/health` → `ok`, `kakao_token_set`, `action_token_set`, `p95_ms`, `api_calls_total`.

세션·카운터는 `data/agent.sqlite3`(WAL)에 있어 재시작해도 대화 상태와 누적 호출 수가 유지된다.

## 2. 심사 직전 점검(16:00 전)

- [ ] 공개 TC 1~2개로 `scripts/cli_chat.py --tc <ID>` 실행 → 접수번호가 실제로 남는지, 답변 500자 이내인지.
- [ ] 공개 TC 사례 화면의 모범 처리에서 **TC ID가 대화에 어떻게 오는지**, **인입 계정이 어떻게 표시되는지**, **에스컬레이션 lane 값 형식**을 확인하고 필요하면 `.env`만 조정:
  - TC ID 표기가 파서에 안 잡히면: 파서 정규식(`gyodong_agent/parser.py`) 또는 LLM의 `set_test_case_id` 도구가 처리. 
  - 인입 계정 표기가 안 잡히면: `INBOUND_MARKER_REGEX` 조정. 인입 계정 표시 자체가 없는 형식이면 `AUTH_MODE=lenient`.
  - lane 형식이 다르면 `ESCALATION_LANE_FORMAT` (`{lane}` / `{lane}:{target}` / `{target}`).
- [ ] 연습 접수가 쌓여 있으면 필요 시 `python3 scripts/admin_reset_practice_data.py --yes-reset-practice-data` (최종 제출 전만. 평가 시작 시 자동 초기화).
- [ ] `.env`의 `DEFAULT_TC_ID`는 **비워 둔다**(평가는 대화의 TC ID 사용).
- [ ] `/health`의 `kakao_token_set`, `action_token_set`가 true.

## 3. 심사 중(2026-10-31 16:00 ~ 11-01 24:00)

- 시나리오·프롬프트·배포 변경 금지. 코드·`.env` 수정 금지.
- 허용되는 것: 프로세스 재시작(같은 코드), 터널 재연결, GPU 상태 확인.
- 모니터링: `tail -f data/audit.jsonl` (사용자 키는 해시, 전화번호·토큰은 마스킹) · `/health`의 `callback_fail`, `p95_ms`.
- 누적 3,000 한도: `api_calls_total`을 확인. 한도가 소진되면 클라이언트가 이후 호출을 중단하고 답변은 계속한다.

## 4. 장애 대응

| 증상 | 확인 | 조치 |
|---|---|---|
| 답장이 안 감 | `/health` callback_fail, audit `cb` | 카카오 토큰·터널 주소 확인, 서버 재시작 |
| 답변이 공통 오류문 | audit `error` | LLM 서버(8000) 생존 확인 → `scripts/start_llm.sh` 재기동 |
| API 401 | audit `ops` 에 `:401` | ACTION_TOKEN, API 사용 기간 |
| API 400 + MISSING/INVALID_TEST_CASE_ID | TC ID 파싱 | 대화의 TC ID 표기 확인 |
| 429 누적 | 메시지 `누적 API 호출 한도를 초과했습니다.` | 복구 불가 — 답변은 조회 없이 정책 안내로 계속 |

## 5. 로그·개인정보

- `data/audit.jsonl`: 대화 해시 키, 질문·답변(전화번호·토큰 마스킹, 600자), 호출 op/상태, 접수번호, 지연.
- 원본 웹훅 페이로드와 콜백 토큰은 저장하지 않는다(기존 `kakao_bot.py`의 raw_payload 저장 방식을 폐기).
- 세션 TTL 6시간 후 자동 삭제. 대회 종료 후 `data/` 삭제 권장.
