# 교동이 실행 가이드 (Vast.ai 빠른 실행 요약)

전체 절차·문제 해결은 [`VASTAI_GUIDE.md`](VASTAI_GUIDE.md). 이 문서는 핵심만 추린 요약이다.
모델 서버(8000)·상담 서버(9000)·터널을 **한 인스턴스**에서 tmux 세션으로 띄운다.

> 제출 마감 **2026-10-31(토) 15:00**(1회). 제출 후 11-01 24:00까지 코드·`.env`·배포 변경 금지, 인스턴스·터널 유지.

## 저장소·브랜치

- 저장소: https://github.com/hojin2040290/aitop100prelim
- 실행 기준 브랜치: **`main`** (`claude/sweet-ramanujan-jwf1li`와 같은 내용)
- `main`이 GitHub 기본 브랜치가 아니면 clone 할 때 `-b main`을 붙인다.
- `-b main` 없이 받으려면 GitHub 저장소 **Settings → General → Default branch**에서 `main`으로 바꾼다(브랜치 전환 아이콘 → `main` 선택 → Update).
- 원본 자료 71개는 `reference/original_sources/`, 텍스트 추출본은 `reference/source_text/`.

## 인스턴스 선택

| 항목 | 값 |
|---|---|
| 템플릿 | **PyTorch (Vast)** — `setup.sh`가 `/venv/main`·`uv`를 사용 |
| 접속 | SSH (Jupyter 병행 가능) |
| CUDA | 13.2 이미지 사용 가능. **ARM 선택 금지**(x86_64 호스트) |
| GPU | RTX 5090 32GB |
| 디스크 | 권장 120GB 이상. **75GB면 vLLM + vLLM용 NVFP4 모델 하나만** 설치(`setup.sh auto` 금지, SGLang 생략) |
| 대여 | **on-demand**(중단형 금지), 11-02 이후까지 잔액 |

실제 사용 인스턴스 기록(2026-10-31):

| 인스턴스 | 사양 | 상태 |
|---|---|---|
| 58492646 | RTX 5090, EPYC 9135(8 vCPU), RAM 64GB, 디스크 75GB, CUDA 13.2 | 서버 실행 전 오류로 교체 |
| **58492887** | RTX 5090, Ryzen 7 9700X(16 스레드), RAM 126GB, WD_BLACK SN850X 디스크 120GB, CUDA 13.2, 2.2Gbps | **사용 중** |

## 순서 (각 명령은 `/workspace/aitop100prelim`에서 실행)

1. 코드 받기:

```bash
cd /workspace && git clone -b main https://github.com/hojin2040290/aitop100prelim.git && cd aitop100prelim
```

2. 에이전트 설치와 단위 테스트(`.env`가 없으면 자동 생성):

```bash
bash scripts/install_agent.sh
```

3. API 키 설정 — `ACTION_TOKEN`, `KAKAO_BOT_TOKEN`, `ADMIN_TOKEN`을 채우고 `DEFAULT_TC_ID`는 비워 둔다(`.env`는 깃허브에 올라가지 않음):

```bash
nano .env
```

4. 모델 설치(vLLM + Qwen3.8-27B NVFP4, 기존 `serve.sh` 그대로). vLLM 설치 10~20분, 첫 실행 시 커널 컴파일 수 분:

```bash
bash scripts/setup.sh vllm && RUN_ENGINES=vllm bash scripts/setup.sh nvfp4
```

```bash
tmux new -d -s llm 'cd /workspace/aitop100prelim && bash scripts/start_llm.sh 2>&1 | tee data/llm.log'
```

디스크 확인(75GB 인스턴스):

```bash
df -h /workspace
```

5. 상담 서버와 터널:

```bash
tmux new -d -s bot 'cd /workspace/aitop100prelim && bash scripts/run_server.sh'
```

```bash
tmux new -d -s tunnel 'cd /workspace/aitop100prelim && bash scripts/start_tunnel.sh 2>&1 | tee data/tunnel.log'
```

6. 작동 테스트(공개 TC 사용):

```bash
TC=<공개TC_ID> bash scripts/check_all.sh
```

```bash
python3 scripts/cli_chat.py --tc <공개TC_ID>
```

7. 카카오 연결 — 터널 주소를 확인해 Kakao Developers 웹훅 URL에 `https://<터널주소>/kakao/webhook` 등록, 카카오톡으로 실제 대화 1회 후 **App ID와 디브리프 제출**:

```bash
grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' data/tunnel.log | head -1
```

## 서버 상태 점검 (설치 후·설정 변경 후·제출 직전 매번)

1. Action API 토큰 확인 — `HTTP 200`(또는 404)이면 정상, 401 `UNAUTHORIZED`면 `.env`의 `ACTION_TOKEN`이 틀린 것(대회 홈페이지에서 `aitop100_`부터 끝까지 다시 복사, 따옴표·`Bearer `·공백 금지):

```bash
cd /workspace/aitop100prelim && set -a && . ./.env && set +a && curl -s -o /dev/null -w "HTTP %{http_code}\n" -H "Authorization: Bearer $ACTION_TOKEN" -H "X-Aitop100-Test-Case-Id: L-03" https://gyodong-mall-action.aitop100.org/api/products/WTM-SEL-8
```

토큰 형식만 확인(앞 12자와 길이만 출력):

```bash
grep -n "^ACTION_TOKEN" .env | sed -E 's/(ACTION_TOKEN=.{12}).*/\1…(생략)/'; awk -F= '/^ACTION_TOKEN/{print "길이:",length($2)}' .env
```

2. 최신 코드 반영 + 상담 서버 재시작(`.env`를 바꾼 뒤에도 필수). 이전 대화 기록까지 지우려면 `rm` 포함 — **제출 전에만**:

```bash
git pull && tmux kill-session -t bot; rm -f data/agent.sqlite3*; tmux new -d -s bot 'cd /workspace/aitop100prelim && bash scripts/run_server.sh'
```

3. 세션 확인 — `llm`, `bot`, `tunnel` 세 개:

```bash
tmux ls
```

4. 전체 상태 — `ok`, `llm_alive`, `kakao_token_set`, `action_token_set`이 모두 `true`:

```bash
curl -s http://127.0.0.1:9000/health; echo
```

5. 일괄 점검(단위 테스트·모델 서버·Action API·`/chat`). `ADMIN_TOKEN`이 비어 있으면 `/chat` 단계만 실패로 나온다:

```bash
TC=L-03 bash scripts/check_all.sh
```

6. 터널 주소 — 카카오 콘솔에 등록한 주소와 같아야 한다:

```bash
grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' data/tunnel.log | head -1
```

7. 모델 서버 로그·상담 서버 화면:

```bash
grep -E "Application startup complete|Error" data/llm.log | tail -3
```

```bash
tmux capture-pane -pt bot | tail -20
```

## 카카오톡(폰) 시험 방법

1. 채널 관리자센터에서 채널 URL(`pf.kakao.com/_xxxx`) 확인 → 폰에서 열기 → 채널 추가 → 채팅.
2. `안녕하세요`로 연결 확인(답장이 오면 웹훅·콜백 정상).
3. 공개 TC는 **"초기 대화" 블록 전체(case metadata 포함)를 한 메시지로** 붙여넣는다. 예(L-03, `reference/public_tc_L-03.md`):

```text
case metadata
- id: L-03
- 상담 인입 일시: 2037-06-30(화) 15:16
- 인입창구: 조합몰 1:1 채팅
- 인입 계정: 회원 로그인 · 서지호 · 019-****-5231

주소 잘못 넣었어요. 경기 성남시로 바꿔주세요.
```

   에이전트는 여기서 TC ID(`id: L-03`), 인입 계정(이름·마스킹 번호), 현재 시각(인입 일시)을 읽는다. 메타데이터 없이 문의만 보내면 TC ID가 없어 API를 호출하지 않는다.
4. 같은 TC ID로 다시 시험하면 이전 대화가 이어진다. 새로 시작하려면 위 2단계의 `rm -f data/agent.sqlite3*` 후 재시작하거나 다른 공개 TC ID를 쓴다.
5. 매 턴 결과:

```bash
tail -n 1 data/audit.jsonl
```

   - `ops`: 호출 API:상태[:오류코드] — L-03 1턴 `API-13:200`(인입 계정 확인), 주문번호 턴 `API-07:200`·`API-11:200`, 주소 턴 `API-24:200`
   - `receipts`: 접수번호, `cb`: 200이면 카카오 답장 전송 성공, `a_len`: 글자 수, `ms`: 지연
   - `API-13:401:UNAUTHORIZED` → 토큰 문제(점검 1), `cb` 401/403 → `KAKAO_BOT_TOKEN` 문제, 기록 없음 → 웹훅 URL 문제

## 지금까지 겪은 문제와 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| clone 후 테스트에서 `actions.json` 없음 | `.gitignore`가 `gyodong_agent/data/`까지 제외 | 수정됨 — `git pull` |
| `flashinfer-cubin==… 없음` | 미리 컴파일된 커널 미제공 | 무시해도 됨(첫 실행 때 직접 컴파일) |
| `fp4_gemm_cutlass_sm120` 빌드 메시지 | NVFP4 커널 첫 컴파일 | 수 분 대기 |
| 봇이 "회원이 일치하지 않습니다" | 실제로는 Action API 401(토큰 오류) | 토큰 재입력 → 상담 서버 재시작. 코드도 오류를 '불일치'로 말하지 않게 수정됨 |
| 웹훅 주소에 다른 경로가 필요한가 | 아니다 | `https://<터널주소>/kakao/webhook` 하나 |
| `/chat` 단계 실패 | `ADMIN_TOKEN` 비어 있음 | `openssl rand -hex 16` 값을 넣거나 무시 |

## 지켜야 할 것

- 임시 터널(trycloudflare) 주소는 재시작하면 바뀐다. **제출 후에는 터널 세션과 인스턴스를 끄지 않는다** — 주소가 바뀌면 웹훅 URL을 다시 바꿔야 하고, 심사 중에는 배포 변경에 해당할 수 있다.
- 공개 TC에서 인입 계정이나 에스컬레이션 lane 형식이 다르면 **제출 전에** `.env`의 `INBOUND_MARKER_REGEX`, `AUTH_MODE`, `ESCALATION_LANE_FORMAT`만 고친다. 증상별 해결은 `VASTAI_GUIDE.md` 11절.
- 모델 서버 시작 중 `Killed`(메모리 부족)면:

```bash
tmux kill-session -t llm; tmux new -d -s llm 'cd /workspace/aitop100prelim && MAX_JOBS=2 bash scripts/start_llm.sh 2>&1 | tee data/llm.log'
```

## 검증 상태

- 단위 테스트 81건 통과(가짜 Action API·가짜 LLM).
- 이 가이드를 실제 Vast.ai 서버에서 끝까지 실행한 기록은 아직 없다(개발 환경에 GPU 없음). 실행 결과·측정값은 `GPU_ENV.md` 표에 기록한다.
