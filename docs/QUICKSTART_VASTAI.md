# Vast.ai 빠른 실행 요약

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
