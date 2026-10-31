#!/usr/bin/env bash
# Vast.ai(PyTorch 템플릿) 최초 1회 준비: 에이전트 전용 가상환경 + 도구 설치 + .env 생성 + 단위 테스트.
#   bash scripts/vastai_bootstrap.sh            # 에이전트 환경만
#   WITH_LLM=1 bash scripts/vastai_bootstrap.sh # + vLLM 설치 + NVFP4 모델 다운로드(약 17GB)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
W="${W:-/workspace}"
echo "== 1) 시스템 도구(tmux, curl)"
command -v tmux >/dev/null || (apt-get update -qq && apt-get install -y -qq tmux curl >/dev/null)
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }

echo "== 2) 에이전트 가상환경 $W/venv-agent (vLLM 환경과 분리)"
uv venv "$W/venv-agent" --python 3.12 --allow-existing
uv pip install --python "$W/venv-agent/bin/python" -q -r requirements.txt

echo "== 3) .env"
if [ ! -f .env ]; then cp .env.example .env; echo "  .env 생성 — ACTION_TOKEN, KAKAO_BOT_TOKEN, ADMIN_TOKEN 을 채우세요: nano $ROOT/.env"; fi
chmod 600 .env
mkdir -p data

echo "== 4) 단위 테스트(가짜 API·가짜 LLM, 네트워크·GPU 불필요)"
"$W/venv-agent/bin/python" -m pytest -q -p no:warnings

if [ "${WITH_LLM:-0}" = 1 ]; then
  echo "== 5) vLLM 설치 + NVFP4 모델 다운로드(기존 setup.sh)"
  RUN_ENGINES="${RUN_ENGINES:-vllm}" bash scripts/setup.sh vllm
  RUN_ENGINES="${RUN_ENGINES:-vllm}" bash scripts/setup.sh nvfp4
fi
echo "완료. 다음: nano .env → bash scripts/start_all.sh"
