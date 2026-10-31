#!/usr/bin/env bash
# 작동 점검 일괄 실행: 단위 테스트 → 모델 서버 → 상담 서버 /health → (선택) Action API·대화 테스트
#   bash scripts/check_all.sh                 # 1~3단계
#   TC=<공개TC_ID> bash scripts/check_all.sh  # 4~5단계 포함(연습 호출 발생, 제출 전에만)
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-/venv/main/bin/python}"; [ -x "$PY" ] || PY="$(command -v python3)"
set -a; [ -f .env ] && . ./.env; set +a
ok(){ echo "  [OK] $*"; }; ng(){ echo "  [실패] $*"; FAIL=1; }; FAIL=0
echo "1) 단위 테스트"; "$PY" -m pytest -q >/tmp/pytest.log 2>&1 && ok "$(tail -1 /tmp/pytest.log)" || { tail -20 /tmp/pytest.log; ng pytest; }
echo "2) 모델 서버 ${LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
curl -sf "${LLM_BASE_URL:-http://127.0.0.1:8000/v1}/models" >/tmp/models.json && ok "$(head -c 200 /tmp/models.json)" || ng "모델 서버 응답 없음 (tmux attach -t llm 확인)"
echo "3) 상담 서버 /health"
curl -sf "http://127.0.0.1:${BOT_PORT:-9000}/health" && echo && ok health || ng "상담 서버 응답 없음 (tmux attach -t bot)"
[ -n "${ACTION_TOKEN:-}" ] && ok "ACTION_TOKEN 설정됨" || ng "ACTION_TOKEN 비어 있음"
[ -n "${KAKAO_BOT_TOKEN:-}" ] && ok "KAKAO_BOT_TOKEN 설정됨" || ng "KAKAO_BOT_TOKEN 비어 있음"
[ -z "${DEFAULT_TC_ID:-}" ] && ok "DEFAULT_TC_ID 비어 있음(평가용 정상)" || echo "  [주의] DEFAULT_TC_ID=$DEFAULT_TC_ID — 제출 전 비우기"
if [ -n "${TC:-}" ]; then
  echo "4) Action API 연결(GET만, TC=$TC)"; "$PY" scripts/smoke_action_api.py --tc "$TC" || ng smoke
  echo "5) 웹훅 경유 대화(/chat)"
  [ -n "${ADMIN_TOKEN:-}" ] || ng "ADMIN_TOKEN 필요"
  curl -s -X POST "http://127.0.0.1:${BOT_PORT:-9000}/chat" -H "X-Admin-Token: ${ADMIN_TOKEN:-}" -H 'Content-Type: application/json' \
    -d "{\"conversation_id\":\"check-$RANDOM\",\"text\":\"TC ID: $TC\\n배송비는 얼마인가요?\"}"; echo
fi
[ "$FAIL" = 0 ] && echo "전체 통과" || { echo "실패 항목이 있습니다"; exit 1; }
