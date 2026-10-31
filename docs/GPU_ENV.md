# GPU·모델 서버 환경 (마스터 프롬프트 K절)

## 1. 우선 환경

| 항목 | 값 |
|---|---|
| GPU 서버 | Vast.ai, NVIDIA GeForce RTX 5090 (32GB, SM120) |
| 모델 | Qwen3.8-27B NVFP4 — vLLM `Inferact/Qwen3.8-27B-NVFP4`, SGLang `nvidia/Qwen3.8-27B-NVFP4` |
| API | OpenAI 호환, 모델 식별자 `qwen`, 포트 8000, 컨텍스트 32,768 |

## 2. 실행 (기존 자산 그대로)

```bash
bash scripts/setup.sh vllm
```

```bash
bash scripts/start_llm.sh
```

`scripts/start_llm.sh` = `ENGINE=vllm QUANT=nvfp4 bash scripts/serve.sh` (기존 serve.sh 무수정 사본). SGLang 비교:

```bash
ENGINE=sglang bash scripts/start_llm.sh
```

기존 serve.sh 가 5090에 이미 적용하는 것(코드 확인 결과):
- vLLM: `--language-model-only`, `--max-num-seqs 4 --max-num-batched-tokens 4096`, CUDA Graph 1·2·4, Blackwell `--kv-cache-dtype fp8`,
  `--enable-auto-tool-choice --tool-call-parser qwen3_coder`, `--reasoning-parser qwen3`, `enable_thinking=false`. 실패 시 `VLLM_EAGER=1`.
- SGLang: flashinfer 어텐션, `fp8_e4m3` KV, prefill CUDA Graph 끔, `--max-running-requests 4`, `--tool-call-parser qwen3_coder`.
- 접두 캐시: vLLM V1·SGLang 모두 기본 활성 → 에이전트 시스템 프롬프트+도구 정의(약 1만 토큰)가 매 요청 재사용된다.

## 3. 에이전트 쪽 대응

- 도구 호출 형식: 네이티브 `tool_calls`, JSON `<tool_call>`, qwen3_coder XML `<function=..><parameter=..>` 모두 해석(`llm.py`), 인자 타입은 API 스키마로 보정(`tools._coerce`).
- 서버가 도구 호출 옵션 없이 떠 있으면 400을 감지해 프롬프트 방식으로 자동 전환.
- 동시 상담 4개로 제한(`LLM_CONCURRENCY`, serve.sh 한도와 일치) — 초과분은 대기.
- `/health`의 `llm_alive`로 모델 서버 생존 확인, 장애 시 접수번호 보존 폴백 답변.
- 엔진·모델을 바꿔도 `.env`의 `LLM_BASE_URL`/`LLM_MODEL`만 바꾸면 된다(핵심 로직 무관).

## 4. 측정 (K4) — 실행 후 아래 표를 채운다

```bash
python3 scripts/bench_llm.py --n 5 --concurrency 1
```

```bash
python3 scripts/bench_llm.py --n 8 --concurrency 4
```

```bash
nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu --format=csv -l 5
```

| 측정 | vLLM NVFP4 | SGLang NVFP4 | 비고 |
|---|---|---|---|
| TTFT median / p95 | 미측정 | 미측정 | bench_llm.py |
| 1회 생성 median / p95 | 미측정 | 미측정 | |
| 도구 판단 일치(5문항) | 미측정 | 미측정 | |
| cached_tokens 비율 | 미측정 | 미측정 | 접두 캐시 효율 |
| VRAM 사용 | 미측정 | 미측정 | nvidia-smi |
| 동시 4 처리 벽시계 | 미측정 | 미측정 | |
| 상담 1건 p95(실제) | 미측정 | 미측정 | 서버 `/health` p95_ms |

**이 개발 환경에는 GPU가 없어 위 값은 하나도 측정하지 못했다.**

## 5. 환경 변경 기록(변경 시 반드시 작성)

| 일시 | 변경 | 이유 | 예상 효과 | 검증 결과 |
|---|---|---|---|---|
| 2026-10-31 | 에이전트 기본 LLM 경로를 기존 serve.sh(NVFP4)로 통일, 별도 hermes 파서 스크립트 폐기 | 기존 자산이 이미 qwen3_coder 도구 파서·5090 메모리 설정을 갖춤 | 검증된 설정 재사용 | 미측정(GPU 없음) |
