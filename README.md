# 교동마을 산지직송 AI 상담 에이전트 (AI TOP 100 2026 예선)

> **제출 마감 2026-10-31(토) 15:00 — App ID·디브리프 1회 제출, 이후 심사 종료(11-01 24:00)까지 코드·프롬프트·배포 변경 금지(규정 제5·7조).** 마스터 프롬프트: `reference/DEVELOPMENT_MASTER_PROMPT.md`(대회 규정·GPU 환경 추가분 포함).

카카오톡 웹훅 → 정책 가드가 걸린 LLM 도구 호출 에이전트 → Action API(40개 업무 API) → SimpleText 1개(500자 이내).

```
Kakao DISPATCH ─► /kakao/webhook (즉시 200, 이벤트 중복 제거)
                    └─ background: Agent.handle(conv, text)
                         ├ parser: TC ID · 채널 인입 계정 머리말
                         ├ 인입 계정 → API-12/13 대조 → 인증 회원 확정
                         ├ LLM(Qwen, OpenAI 호환) ↔ 도구 49개
                         │    · API_01~API_40 (API-35는 escalate 로 감쌈, reset 미노출)
                         │    · policy_* 결정적 계산기(영업일·컷오프·하자 기한·가격 인하·중량·쿠폰 기간)
                         ├ ToolExecutor 가드: 주문 귀속·개인정보 마스킹·POST 사전검증·중복 접수 방지·5만원 재량
                         └ text_out: 마크다운 제거·500자
                    └─ POST kapi /v1/bot/callback (SimpleText 1개)
```

## 빠른 시작

**요약: [`docs/QUICKSTART_VASTAI.md`](docs/QUICKSTART_VASTAI.md)** (브랜치는 `main` — 기본 브랜치가 아니면 `git clone -b main ...`, 기본 브랜치 변경법 포함)

**Vast.ai에서 처음부터 실행·테스트하는 전체 절차는 [`docs/VASTAI_GUIDE.md`](docs/VASTAI_GUIDE.md)** (인스턴스 선택, API 키 설정, 모델 서버, 상담 서버, 공개 TC 테스트, 카카오 연결, 제출·심사 중 운영).


**Vast.ai 서버 전체 절차(설치·API 키·기동·테스트·제출): [`docs/VASTAI_GUIDE.md`](docs/VASTAI_GUIDE.md)**


```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env   # ACTION_TOKEN, KAKAO_BOT_TOKEN 입력
```

```bash
bash scripts/setup.sh vllm         # GPU 서버(Vast.ai RTX 5090) 최초 1회
```

```bash
bash scripts/start_llm.sh          # = ENGINE=vllm QUANT=nvfp4 bash scripts/serve.sh (Qwen3.8-27B NVFP4, 도구 호출 qwen3_coder)
```

```bash
bash scripts/run_server.sh         # 상담 서버(자동 재시작), 127.0.0.1:9000
```

```bash
bash scripts/start_tunnel.sh   # 공개 주소 → 카카오 디벨로퍼스 웹훅 URL에 https://<주소>/kakao/webhook
```

연습(카카오 없이):

```bash
python3 scripts/smoke_action_api.py --tc <공개TC_ID>     # 토큰·TC 헤더·응답 형식 확인(GET만)
```

```bash
python3 scripts/cli_chat.py --tc <공개TC_ID>             # 실제 LLM+API로 대화
```

테스트:

```bash
python3 -m pytest -q
```

## 디렉터리

| 경로 | 내용 |
|---|---|
| `gyodong_agent/api_registry.py` | actions.json → 41개 Operation(쿼리 포함 path key 분리, 스키마 검증, 계수 불일치 시 실패) |
| `gyodong_agent/action_client.py` | 헤더·레이트리밋·429/500/503 처리·누적 한도 감지, reset은 관리자 메서드만 |
| `gyodong_agent/tools.py` | LLM 도구 정의 + 가드(귀속·마스킹·POST 사전검증·중복 방지·재량 한도) |
| `gyodong_agent/policy.py`, `calendar2037.py` | 결정적 정책 계산기, 2037 영업일·공휴일 |
| `gyodong_agent/knowledge.py` | 시스템 프롬프트(규정 요약) |
| `gyodong_agent/agent.py` | 에이전트 루프(데드라인 50초, 최대 8스텝, 실패 시 접수번호 보존 폴백) |
| `gyodong_agent/server.py` | FastAPI 웹훅·콜백·/health·/chat |
| `reference/` | 원문 텍스트 추출본, 메타데이터, 요구사항 문서, 기존 스크립트(legacy) |
| `gyodong_agent/security.py` | 프롬프트 인젝션 방어(입력 제한·탐지·누출 차단·대화별 속도 제한, 규정 제7조) |
| `scripts/serve.sh`, `setup.sh`, `bench_llm.py` | 기존 모델 서버 스크립트(무수정) + TTFT·지연 측정 |
| `docs/` | 운영 가이드(제출 마감 15:00), 제출·규정 체크리스트, GPU 환경, 미확보·미검증 목록 |

원본 자료 71개(PNG·PDF·XLSX 등)는 `reference/original_sources/`, 텍스트 추출본은 `reference/source_text/`에 있고,
이미지에만 있는 권한 위임표(B10)·수산물 중량 세칙(B13)은 시각 검토해 `knowledge.py`·`policy.py`에 반영했다.
