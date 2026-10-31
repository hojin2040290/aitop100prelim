# Vast.ai 실행·작동 테스트 가이드 (처음부터 끝까지)

모델 서버(vLLM, 8000)·상담 서버(9000)·Cloudflare 터널을 **같은 Vast.ai 인스턴스 하나**에서 tmux 세션 3개로 띄운다.

> 제출 마감 **2026-10-31 15:00**(1회). 제출 후 11-01 24:00까지 코드·`.env`·배포 변경 금지, 인스턴스·터널은 계속 켜 둔다.

## 0. 인스턴스 만들기

| 선택 | 값 |
|---|---|
| 템플릿 | **PyTorch (Vast)** — `/venv/main`·`uv`가 들어 있어 `setup.sh`가 그대로 동작 |
| 실행 방식 | **SSH** (Jupyter도 함께 켜도 됨 — 브라우저 터미널로 써도 된다) |
| CUDA | 13.2 이미지 선택 가능. RTX 5090(Blackwell)은 드라이버 CUDA 12.8 이상 호스트여야 함 |
| ARM | **선택하지 않는다**(x86_64 호스트). vLLM·SGLang·NVFP4 휠은 x86_64 기준으로 검증됨 |
| GPU | RTX 5090 ×1 (32GB) |
| 디스크 | **120GB 이상** (NVFP4 모델 2개 약 34GB + vLLM·SGLang 가상환경 + 캐시) |
| 기간·잔액 | **11-02(월) 이후까지** 유지되도록(규정 제7조). 중단형(interruptible)이 아닌 on-demand |

SSH 접속(Vast 콘솔의 Connect 버튼에 나오는 명령):

```bash
ssh -p <포트> root@<IP> -L 8080:localhost:8080
```

접속 후 tmux가 자동으로 붙는 템플릿이면 `Ctrl+b d`로 빠져나와도 작업은 계속 돈다.

## 1. 코드 받기

```bash
cd /workspace && git clone https://github.com/hojin2040290/aitop100prelim.git && cd aitop100prelim
```

비공개 저장소라면 GitHub 개인 액세스 토큰(Contents: Read)을 만들어:

```bash
cd /workspace && git clone https://<GitHub사용자명>:<토큰>@github.com/hojin2040290/aitop100prelim.git && cd aitop100prelim
```

## 2. 에이전트 설치 + 단위 테스트

```bash
bash scripts/install_agent.sh
```

끝에 `81 passed`(또는 그 이상)가 나와야 한다. `.env`가 없으면 `.env.example`로 만들어 준다.

## 3. API 키·환경 설정 (`.env`)

```bash
nano .env
```

반드시 채울 값:

| 키 | 값 | 어디서 |
|---|---|---|
| `ACTION_TOKEN` | `aitop100_...` 전체 | 대회 홈페이지의 액션 토큰 |
| `KAKAO_BOT_TOKEN` | 카카오 봇 인증 토큰 | Kakao Developers > 내 앱 > 카카오톡 봇(채널 챗봇) 설정 |
| `ADMIN_TOKEN` | 임의의 긴 문자열 | 로컬 `/chat` 테스트용(외부 노출 안 함) |
| `DEFAULT_TC_ID` | **비워 둔다** | 평가 때는 대화에 오는 TC ID 사용 |

그대로 두면 되는 값: `LLM_BASE_URL=http://127.0.0.1:8000/v1`, `LLM_MODEL=qwen`, `BOT_PORT=9000`, `LLM_CONCURRENCY=4`.

공개 TC 화면을 보고 필요하면 조정:
- 인입 계정 표기가 다르면 `INBOUND_MARKER_REGEX`, 인입 계정 표시가 아예 없는 형식이면 `AUTH_MODE=lenient`
- 에스컬레이션 lane 형식이 다르면 `ESCALATION_LANE_FORMAT` (`{lane}` / `{lane}:{target}` / `{target}`)

권한 확인:

```bash
chmod 600 .env && grep -c "aitop100_" .env
```

`.env`는 `.gitignore`에 있어 커밋되지 않는다. 절대 깃허브에 올리지 말 것.

## 4. 모델 서버 설치·실행 (Qwen3.8-27B NVFP4)

vLLM 설치(10~20분):

```bash
bash scripts/setup.sh vllm
```

NVFP4 모델 내려받기(vLLM용만):

```bash
RUN_ENGINES=vllm bash scripts/setup.sh nvfp4
```

tmux 세션 `llm`에서 실행:

```bash
tmux new -d -s llm 'cd /workspace/aitop100prelim && bash scripts/start_llm.sh 2>&1 | tee data/llm.log'
```

`Application startup complete`가 나올 때까지 기다린다(첫 실행은 커널 컴파일로 수 분):

```bash
tail -f data/llm.log
```

확인:

```bash
curl -s http://127.0.0.1:8000/v1/models
```

시작 실패 시(메모리·CUDA Graph 문제) 예비 방식:

```bash
tmux kill-session -t llm; tmux new -d -s llm 'cd /workspace/aitop100prelim && VLLM_EAGER=1 bash scripts/start_llm.sh 2>&1 | tee data/llm.log'
```

SGLang으로 비교하려면(같은 GPU라 vLLM을 먼저 끈다):

```bash
bash scripts/setup.sh sglang && RUN_ENGINES=sglang bash scripts/setup.sh nvfp4
```

```bash
tmux kill-session -t llm; tmux new -d -s llm 'cd /workspace/aitop100prelim && ENGINE=sglang bash scripts/start_llm.sh 2>&1 | tee data/llm.log'
```

## 5. 모델 성능 측정

```bash
python3 scripts/bench_llm.py --n 5 --concurrency 1
```

```bash
python3 scripts/bench_llm.py --n 8 --concurrency 4
```

```bash
nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu --format=csv
```

출력의 TTFT·지연·도구 판단 일치 수를 `docs/GPU_ENV.md` 표에 기록한다. 도구 판단이 5개 중 3개 이하이면 도구 호출 파서가 안 맞는 것이므로 `data/llm.log`에서 오류를 확인한다.

## 6. 상담 서버 실행

```bash
tmux new -d -s bot 'cd /workspace/aitop100prelim && bash scripts/run_server.sh'
```

```bash
curl -s http://127.0.0.1:9000/health
```

`ok: true`, `llm_alive: true`, `kakao_token_set: true`, `action_token_set: true`가 나와야 한다.

## 7. 공개 TC로 실제 작동 테스트 (제출 전에만 — 연습 호출)

Action API 연결(GET만):

```bash
python3 scripts/smoke_action_api.py --tc <공개TC_ID>
```

200 응답이 나오면 토큰·TC 헤더가 맞다. 401이면 토큰, 400 `INVALID_TEST_CASE_ID`면 TC ID 오류.

터미널 대화(실제 LLM + 실제 API):

```bash
python3 scripts/cli_chat.py --tc <공개TC_ID>
```

공개 TC의 고객 질문을 그대로 입력한다. 인입 계정이 있는 사례면 첫 입력을 이렇게(여러 줄은 줄 끝 `\`):

```text
[인입 계정] 명의: 홍길동 / 연락처: 010-1234-5678\
수박이 하나도 안 달아요. 환불해 주세요.
```

확인할 것: 답변 500자 이하, 출력 줄의 `호출:`이 모범 처리의 API 순서와 비슷한지, `접수:`에 실제 접수번호가 찍히는지, 공개 TC의 기대 처리와 결론이 같은지.

서버 경유 일괄 점검:

```bash
TC=<공개TC_ID> bash scripts/check_all.sh
```

연습 접수가 많이 쌓여 다른 TC 결과가 꼬이면(최종 제출 전만 가능):

```bash
python3 scripts/admin_reset_practice_data.py --yes-reset-practice-data
```

## 8. 카카오톡 연결

```bash
tmux new -d -s tunnel 'cd /workspace/aitop100prelim && bash scripts/start_tunnel.sh 2>&1 | tee data/tunnel.log'
```

```bash
grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' data/tunnel.log | head -1
```

Kakao Developers > 앱 > 카카오톡 봇 설정의 웹훅 URL에 `https://<위 주소>/kakao/webhook` 등록 → 카카오톡 채널에서 직접 메시지 보내기 → 답장 확인.

```bash
tail -n 5 data/audit.jsonl
```

`cb`가 200이면 콜백 성공. 실패면 `KAKAO_BOT_TOKEN`, 웹훅 URL 확인.

**주의**: 임시 터널(`trycloudflare`)은 재시작하면 주소가 바뀐다. 제출 후에는 **터널 세션을 절대 끄지 않는다**(주소가 바뀌면 콘솔 URL을 다시 바꿔야 하고, 이는 심사 중 배포 변경에 해당할 수 있다). 인스턴스 재부팅도 피한다.

## 9. 제출 (15:00 전)

```bash
bash scripts/check_all.sh
```

전체 통과 → 카카오톡 실대화 1회 성공 확인 → Kakao Developers **App ID + 디브리프 제출**. 제출 시점 기록:

```bash
git log --oneline -1 > data/SUBMITTED_COMMIT && date >> data/SUBMITTED_COMMIT
```

## 10. 심사 중(~11-01 24:00) 할 일·하지 말 일

- 하지 말 것: 코드·`.env`·프롬프트 수정, `git pull`, 터널 재시작, 웹훅 URL 변경, Action API 수동 호출, 인스턴스 중지.
- 해도 되는 것(같은 코드 재기동): 모델 서버가 죽었으면 `tmux new -d -s llm ...`(4절 명령) 재실행. 상담 서버는 `run_server.sh`가 자동 재시작한다.
- 모니터링:

```bash
curl -s http://127.0.0.1:9000/health
```

```bash
tail -f data/audit.jsonl
```

```bash
tmux ls
```

## 11. 문제 해결

| 증상 | 원인·조치 |
|---|---|
| `setup.sh` 에서 `uv: command not found` | PyTorch(Vast) 템플릿이 아님 → `pip install uv` 후 재실행 |
| vLLM 시작 중 `Killed` (nvcc) | RAM 부족 커널 컴파일 → `MAX_JOBS=2 bash scripts/start_llm.sh` |
| CUDA out of memory | 다른 프로세스가 GPU 사용 중(`nvidia-smi`) → 정리 후 재시작, 또는 `VLLM_EAGER=1` |
| `/health` `llm_alive:false` | `tmux attach -t llm`으로 로그 확인 후 재기동 |
| 답변이 "일시적인 문제" 공통문 | `data/audit.jsonl`의 `error` 확인(LLM 타임아웃이면 `AGENT_MAX_STEPS` 축소 — 제출 전만) |
| 모든 주문 처리가 막힘(UNVERIFIED) | 인입 계정 표기 미인식 → `INBOUND_MARKER_REGEX` 또는 `AUTH_MODE=lenient` (제출 전만) |
| API 400 `MISSING_TEST_CASE_ID` | 대화에서 TC ID 표기를 못 읽음 → 공개 TC 표기 확인 |
