#!/usr/bin/env bash
# 모델 서버 실행 — 기존 serve.sh 를 그대로 사용(Vast.ai RTX 5090 32GB, Qwen3.8-27B NVFP4 우선).
#   bash scripts/start_llm.sh                      # = ENGINE=vllm QUANT=nvfp4 (Inferact/Qwen3.8-27B-NVFP4)
#   ENGINE=sglang bash scripts/start_llm.sh        # = nvidia/Qwen3.8-27B-NVFP4
# serve.sh 는 이미 도구 호출(--enable-auto-tool-choice --tool-call-parser qwen3_coder),
# reasoning-parser qwen3, enable_thinking=false, 5090용 fp8 KV 캐시·동시 4요청 설정을 갖고 있다.
# 처음 한 번: bash scripts/setup.sh vllm   (또는 sglang)
set -euo pipefail
cd "$(dirname "$0")"
export ENGINE="${ENGINE:-vllm}" QUANT="${QUANT:-nvfp4}" PORT="${PORT:-8000}" CTX="${CTX:-32768}"
exec bash ./serve.sh
