#!/usr/bin/env bash
# 상담 서버 실행(자동 재시작 루프). 사용: bash scripts/run_server.sh
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
while true; do
  echo "[$(date '+%F %T')] 서버 시작"
  python3 -m gyodong_agent.server
  code=$?
  echo "[$(date '+%F %T')] 서버 종료(code=$code) — 3초 후 재시작" | tee -a data/restarts.log
  sleep 3
done
