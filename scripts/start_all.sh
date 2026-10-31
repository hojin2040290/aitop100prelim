#!/usr/bin/env bash
# tmux 세션 3개로 전체 기동: llm(모델 서버) → agent(상담 서버) → tunnel(공개 https 주소)
#   bash scripts/start_all.sh          # 전부
#   SKIP_LLM=1 bash scripts/start_all.sh  # 모델 서버가 이미 떠 있을 때
# 확인: tmux ls / tmux attach -t llm (빠져나오기: Ctrl+b 다음 d)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"; W="${W:-/workspace}"; mkdir -p data
PY="$W/venv-agent/bin/python"; [ -x "$PY" ] || PY=python3
[ -f .env ] || { echo ".env 가 없습니다: cp .env.example .env 후 값 입력"; exit 1; }
grep -q '^ACTION_TOKEN=aitop100_' .env || echo "경고: .env 의 ACTION_TOKEN 이 비었거나 aitop100_ 로 시작하지 않습니다"
grep -q '^KAKAO_BOT_TOKEN=.\+' .env || echo "경고: .env 의 KAKAO_BOT_TOKEN 이 비었습니다(카카오 답장이 실패합니다)"

if [ "${SKIP_LLM:-0}" != 1 ] && ! tmux has-session -t llm 2>/dev/null; then
  tmux new-session -d -s llm "cd $ROOT && bash scripts/start_llm.sh 2>&1 | tee -a data/llm.log"
  echo "모델 서버 시작(첫 기동은 커널 컴파일로 수 분~20분). 대기 중..."
fi
for i in $(seq 1 180); do
  curl -sf http://127.0.0.1:8000/v1/models >/dev/null && { echo "모델 서버 준비됨"; break; }
  sleep 10
  [ "$i" = 180 ] && { echo "30분 내 모델 서버가 뜨지 않음 → tail -n 80 data/llm.log"; exit 1; }
done

tmux has-session -t agent 2>/dev/null || \
  tmux new-session -d -s agent "cd $ROOT && AGENT_PY=$PY bash scripts/run_server.sh 2>&1 | tee -a data/agent.log"
sleep 3
curl -sf http://127.0.0.1:9000/health && echo

if ! tmux has-session -t tunnel 2>/dev/null; then
  tmux new-session -d -s tunnel "cd $ROOT && bash reference/legacy/start_tunnel.sh 2>&1 | tee -a data/tunnel.log"
  for i in $(seq 1 30); do
    URL="$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' data/tunnel.log | tail -1 || true)"
    [ -n "$URL" ] && break; sleep 2
  done
  echo "${URL:-주소 미확인}/kakao/webhook" | tee data/webhook_url.txt
fi
echo "카카오 디벨로퍼스 웹훅 URL: $(cat data/webhook_url.txt)"
