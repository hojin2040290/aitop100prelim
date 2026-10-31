#!/usr/bin/env bash
# Qwen3.8-27B를 vLLM으로 띄우는 스크립트 (vast.ai A100 80GB 기준)
#
# 사용법:
#   bash start_vllm.sh              # BF16 원본 (약 56GB)
#   QUANT=fp8 bash start_vllm.sh    # FP8 (약 29GB, 더 빠름, 품질 거의 동일)
#
# 서버가 뜨면 "Application startup complete" 가 출력됩니다.
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen3.8-27B}"
PORT="${PORT:-8000}"

EXTRA=()
if [[ "${QUANT:-}" == "fp8" ]]; then
  EXTRA+=(--quantization fp8)
fi

# 모델 파일은 첫 실행 때 ~/.cache/huggingface 에 받아 두고, 다음부터는 재사용합니다.
vllm serve "$MODEL" \
  --served-model-name qwen \
  --host 127.0.0.1 \
  --port "$PORT" \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.92 \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  "${EXTRA[@]}" \
  "$@"
