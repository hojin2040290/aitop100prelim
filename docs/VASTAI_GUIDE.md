# Vast.ai 실행·작동 테스트 가이드 (RTX 5090 · Qwen3.8-27B NVFP4)

모델 서버와 상담 에이전트를 **같은 Vast.ai 인스턴스 한 대**에서 실행한다.
`카카오톡 → cloudflared 공개 주소 → 에이전트(127.0.0.1:9000) → 모델 서버(127.0.0.1:8000) + Action API`

> 제출 마감 **15:00**(App ID·디브리프 1회). 첫 모델 기동에 10~20분이 걸릴 수 있으니 바로 시작할 것.
> 제출 후 11-01(일) 24:00까지 인스턴스·tmux·터널을 끄지 말고, 코드·`.env`를 고치지 말 것.

## 0. 인스턴스 만들기 (Vast.ai 콘솔)

| 항목 | 선택 |
|---|---|
| Template | **PyTorch (Vast)** — CUDA 13.2 이미지 사용 가능(5090은 CUDA 12.8 이상 드라이버면 됨) |
| CPU 아키텍처 | **x86_64 (ARM 선택하지 않음)** — vLLM·SGLang·cloudflared 설치가 x86 기준으로 검증됨 |
| GPU | RTX 5090 ×1 (32GB) |
| Disk | **120GB 이상**(NVFP4 모델 약 17GB + vLLM 가상환경 + 커널 캐시) |
| Launch mode | **SSH** (Jupyter는 선택 — 파일 확인용으로만) |
| 기간 | **11-02(월) 이후까지** 잔액·예약 확보 |

인스턴스가 뜨면 콘솔의 SSH 명령으로 접속한다(포트·주소는 콘솔에 표시된 값):

```bash
ssh -p <포트> root@<주소>
```

## 1. 프로젝트 받기 (GitHub)

```bash
cd /workspace
```

공개 레포면:

```bash
git clone -b claude/sweet-ramanujan-jwf1li https://github.com/hojin2040290/aitop100prelim.git
```

비공개 레포면 GitHub에서 **Fine-grained token(이 레포 Contents: Read-only)** 을 만든 뒤:

```bash
git clone -b claude/sweet-ramanujan-jwf1li https://hojin2040290:<GITHUB_TOKEN>@github.com/hojin2040290/aitop100prelim.git
```

```bash
cd /workspace/aitop100prelim && git remote set-url origin https://github.com/hojin2040290/aitop100prelim.git
```

(두 번째 명령은 토큰이 `.git/config`에 남지 않게 지운다.) 레포에는 소스·테스트·스크립트·원본 자료 71개(`reference/original_sources/`)가 모두 들어 있다.

## 2. 설치 (에이전트 + vLLM + 모델)

```bash
cd /workspace/aitop100prelim && WITH_LLM=1 bash scripts/vastai_bootstrap.sh
```

하는 일: tmux·uv 설치 → `/workspace/venv-agent`(에이전트 전용) → `.env` 생성(권한 600) → **단위 테스트 81건** → vLLM 설치(`/workspace/venv-vllm`) → `Inferact/Qwen3.8-27B-NVFP4` 다운로드.
마지막 테스트 줄이 `81 passed`면 정상. 모델 다운로드가 인증 오류면 Hugging Face 토큰을 넣고 다시:

```bash
export HF_TOKEN=<허깅페이스_토큰> && bash scripts/setup.sh nvfp4
```

SGLang도 비교하려면(선택):

```bash
RUN_ENGINES=sglang bash scripts/setup.sh sglang && RUN_ENGINES=sglang bash scripts/setup.sh nvfp4
```

## 3. API 키·환경 설정 (`.env`)

```bash
nano /workspace/aitop100prelim/.env
```

반드시 채울 값:

| 키 | 값 |
|---|---|
| `ACTION_TOKEN` | 대회 홈페이지의 액션 토큰(`aitop100_`로 시작, 전체 그대로) |
| `KAKAO_BOT_TOKEN` | Kakao Developers 봇의 인증 토큰(`Authorization: KakaoAK` 뒤에 붙는 값) |
| `ADMIN_TOKEN` | 아무 긴 임의 문자열(로컬 `/chat` 테스트용) |
| `DEFAULT_TC_ID` | **비워 둔다**(평가는 대화의 TC ID 사용) |

그대로 두면 되는 값: `LLM_BASE_URL=http://127.0.0.1:8000/v1`, `LLM_MODEL=qwen`, `BOT_PORT=9000`, `AUTH_MODE=strict`, `ESCALATION_LANE_FORMAT={lane}`.
토큰은 `.env`에만 두고 커밋하지 않는다(`.gitignore`에 포함). 확인:

```bash
grep -c '^ACTION_TOKEN=aitop100_' /workspace/aitop100prelim/.env
```

`1`이 나오면 토큰 형식이 맞다.

## 4. 전체 기동

```bash
cd /workspace/aitop100prelim && bash scripts/start_all.sh
```

tmux 세션 3개가 생긴다: `llm`(모델), `agent`(상담 서버, 죽으면 자동 재시작), `tunnel`(cloudflared).
마지막에 `카카오 디벨로퍼스 웹훅 URL: https://xxxx.trycloudflare.com/kakao/webhook` 이 출력된다(`data/webhook_url.txt`에도 저장).

```bash
tmux ls
```

```bash
tail -n 50 /workspace/aitop100prelim/data/llm.log
```

세션 화면 보기: `tmux attach -t llm` (빠져나오기 `Ctrl+b` 다음 `d`). 모델이 메모리 부족·커널 오류로 안 뜨면 `docs/GPU_ENV.md`와 아래 문제 해결 표 참조.

## 5. 작동 테스트 (순서대로)

### T1. 모델 서버 응답

```bash
curl -s http://127.0.0.1:8000/v1/models
```

`"id":"qwen"`이 보이면 정상.

### T2. 모델 도구 호출·속도

```bash
cd /workspace/aitop100prelim && /workspace/venv-agent/bin/python scripts/bench_llm.py --n 5 --concurrency 1
```

`도구 판단 일치 4/5` 이상, TTFT·생성 시간을 `docs/GPU_ENV.md` 표에 기록. 동시 처리:

```bash
cd /workspace/aitop100prelim && /workspace/venv-agent/bin/python scripts/bench_llm.py --n 8 --concurrency 4
```

```bash
nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu --format=csv
```

### T3. Action API 연결(조회만)

공개 TC 탭에서 TC ID 하나를 골라:

```bash
cd /workspace/aitop100prelim && /workspace/venv-agent/bin/python scripts/smoke_action_api.py --tc <공개TC_ID>
```

`-> 200` 줄이 나오면 토큰·TC 헤더가 정상. `401`=토큰/기간, `400 INVALID_TEST_CASE_ID`=TC ID 확인.

### T4. 에이전트 대화(실제 모델 + 실제 API)

```bash
cd /workspace/aitop100prelim && /workspace/venv-agent/bin/python scripts/cli_chat.py --tc <공개TC_ID>
```

공개 TC 화면의 **고객 질문을 그대로** 입력하고(인입 계정 표시가 있으면 그 줄까지 포함, 여러 줄은 줄 끝에 `\`), 다음을 확인한다:
- 출력의 `호출:` 목록이 모범 처리 과정의 API 순서와 비슷한지, `접수:`에 실제 접수번호가 찍히는지
- 답변이 500자 이내 한 덩어리이고 접수번호를 지어내지 않는지
- `오류: None`

이때 확인해서 `.env`만 조정할 것(코드 수정 불필요):

| 관찰 | 조정 |
|---|---|
| 인입 계정이 있는데 컨텍스트가 "인입 계정 표시 없음"으로 처리됨 | `INBOUND_MARKER_REGEX`에 그 표기 단어 추가 |
| 공개 TC 대화에 인입 계정 표시 자체가 없음 | `AUTH_MODE=lenient` |
| 모범 처리의 에스컬레이션 `lane` 값이 `LANE2_HANDOFF`와 다름 | `ESCALATION_LANE_FORMAT` (`{lane}:{target}` 또는 `{target}`) |

`.env`를 바꿨으면 에이전트만 재시작:

```bash
tmux kill-session -t agent; cd /workspace/aitop100prelim && SKIP_LLM=1 bash scripts/start_all.sh
```

(이미 떠 있는 터널은 그대로 두므로 웹훅 주소가 바뀌지 않는다.) 연습 접수가 쌓여 다음 TC 결과가 헷갈리면 제출 전에만:

```bash
cd /workspace/aitop100prelim && /workspace/venv-agent/bin/python scripts/admin_reset_practice_data.py --yes-reset-practice-data
```

### T5. HTTP 경로(로컬)

```bash
curl -s http://127.0.0.1:9000/health
```

`llm_alive:true`, `action_token_set:true`, `kakao_token_set:true` 확인.

```bash
curl -s -X POST http://127.0.0.1:9000/chat -H "X-Admin-Token: <ADMIN_TOKEN>" -H "Content-Type: application/json" -d '{"conversation_id":"t1","text":"TC ID: <공개TC_ID>\n배송비가 얼마인가요?"}'
```

### T6. 공개 주소 → 웹훅

```bash
curl -s -X POST "$(cat /workspace/aitop100prelim/data/webhook_url.txt)" -H "Content-Type: application/json" -d '{"op":"DISPATCH","d":{"callbackToken":"test-token","botUserKey":"tester","content":"안녕하세요"}}'
```

`{"ok":true}`가 즉시 오면 터널·웹훅 정상(가짜 콜백 토큰이라 카카오 답장 자체는 실패하는 것이 정상).

### T7. 실제 카카오톡

1. Kakao Developers → 봇 설정 → 웹훅 URL에 `data/webhook_url.txt`의 주소 등록·저장.
2. 휴대폰 카카오톡에서 채널 챗봇에 메시지 전송 → 답장 확인.
3. 서버에서 기록 확인:

```bash
tail -n 3 /workspace/aitop100prelim/data/audit.jsonl
```

`"cb": 200`이면 콜백 성공. `cb`가 401/403이면 `KAKAO_BOT_TOKEN`, 오지 않으면 웹훅 URL을 확인.

## 6. 제출과 동결 (15:00 전)

1. T1~T7 통과 확인.
2. 제출 시점 기록(코드 고정):

```bash
cd /workspace/aitop100prelim && git rev-parse HEAD | tee data/submitted_commit.txt
```

3. 대회 페이지에서 **Kakao Developers App ID + 디브리프 제출**(1회).
4. 이후 11-01 24:00까지: `git pull`·코드·`.env` 수정 금지, tmux 세션·인스턴스·터널 종료 금지.
   **cloudflared 임시 터널은 다시 실행하면 주소가 바뀐다** → `tunnel` 세션을 절대 끄지 않는다.

## 7. 심사 중 점검(읽기만)

```bash
curl -s http://127.0.0.1:9000/health
```

```bash
tail -f /workspace/aitop100prelim/data/audit.jsonl
```

```bash
tmux ls
```

## 8. 문제 해결

| 증상 | 확인 | 조치 |
|---|---|---|
| 모델 기동 중 `Killed`(nvcc) | `data/llm.log` | serve.sh가 MAX_JOBS로 제한함. 그래도 나면 `MAX_JOBS=2` 붙여 `tmux kill-session -t llm` 후 재기동 |
| 모델 CUDA 메모리 부족 | `data/llm.log` | `VLLM_EAGER=1 bash scripts/start_llm.sh` 또는 `CTX=16384` |
| vLLM NVFP4 실패 | 로그의 커널/아키텍처 오류 | SGLang으로 전환: `ENGINE=sglang` (설치 필요), `docs/GPU_ENV.md` 변경 기록에 이유·결과 기록 |
| `llm_alive:false` | `tmux attach -t llm` | 모델 세션 재기동(에이전트는 그대로) |
| 답변이 "일시적인 문제" 문구 | `audit.jsonl`의 `error` | 모델 서버·`LLM_BASE_URL` 확인 |
| Action API 401 | `ops`에 `:401` | `ACTION_TOKEN`, API 사용 기간 |
| `NO_TC_ID` | 대화에 TC ID 표기 | 메시지에 TC ID가 있는지, 표기 형식 확인 |
| 카카오 답장 없음 | `cb` 값 | 토큰·웹훅 URL·tunnel 세션 생존 |
| 인스턴스가 재부팅됨 | `tmux ls`가 비어 있음 | `bash scripts/start_all.sh` 재실행 → **터널 주소가 바뀌므로** 웹훅 URL 재등록 필요(제출 후라면 배포 변경에 해당할 수 있어 위험) |
