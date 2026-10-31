#!/usr/bin/env bash
# vLLM 으로 Qwen 서버 실행 — 도구 호출(hermes 파서)과 접두 캐시를 켠다.
#   MODEL=Qwen/Qwen3.8-27B-FP8 bash scripts/start_llm.sh
# 기존 reference/legacy/serve.sh 를 쓸 경우에도 아래 두 옵션을 반드시 추가:
#   --enable-auto-tool-choice --tool-call-parser hermes
# (옵션 없이 떠 있어도 에이전트가 프롬프트 방식 도구 호출로 자동 전환하지만, 네이티브 방식이 더 안정적이다)
set -euo pipefail
MODEL="${MODEL:-Qwen/Qwen3.8-27B-FP8}"
PORT="${PORT:-8000}"
CTX="${CTX:-32768}"
exec vllm serve "$MODEL" \
  --served-model-name qwen \
  --host 127.0.0.1 --port "$PORT" \
  --max-model-len "$CTX" \
  --gpu-memory-utilization "${GPU_UTIL:-0.92}" \
  --enable-prefix-caching \
  --enable-auto-tool-choice --tool-call-parser "${TOOL_PARSER:-hermes}" \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  "$@"
