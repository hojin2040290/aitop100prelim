#!/usr/bin/env bash
# 상담 에이전트(모델 서버 제외) 의존성 설치 + .env 준비. Vast.ai PyTorch 템플릿(/venv/main) 기준.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-/venv/main/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
echo "파이썬: $PY ($("$PY" --version))"
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$PY" -q -r requirements.txt
else
  "$PY" -m pip install -q -r requirements.txt
fi
command -v tmux >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq tmux >/dev/null) || true
mkdir -p data
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo ".env 를 만들었습니다 → nano .env 로 ACTION_TOKEN, KAKAO_BOT_TOKEN, ADMIN_TOKEN 을 채우세요."
fi
"$PY" -m pytest -q
echo "설치·단위 테스트 완료"
