#!/usr/bin/env bash
# 상담 서버 실행(자동 재시작 루프). 사용: bash scripts/run_server.sh
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
# tmux 비대화형 셸에서는 /venv/main 이 활성화되지 않을 수 있어 경로를 직접 지정한다
if [ -z "${AGENT_PY:-}" ]; then
  if [ -x /venv/main/bin/python ]; then AGENT_PY=/venv/main/bin/python; else AGENT_PY=python3; fi
fi
while true; do
  echo "[$(date '+%F %T')] 서버 시작"
  "${AGENT_PY:-python3}" -m gyodong_agent.server
  code=$?
  echo "[$(date '+%F %T')] 서버 종료(code=$code) — 3초 후 재시작" | tee -a data/restarts.log
  sleep 3
done
