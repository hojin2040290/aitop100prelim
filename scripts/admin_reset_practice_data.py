"""[관리자 전용] 연습 데이터 초기화 — POST /api/action-data/reset.

상담 에이전트에는 노출되지 않는다. 모든 TC의 연습 접수 기록이 함께 지워진다.
최종 제출 후·평가 시작 후에는 서버가 409를 돌려주며, 평가 시작 시 자동 초기화되므로 호출할 필요가 없다.

  python3 scripts/admin_reset_practice_data.py --yes-reset-practice-data
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gyodong_agent.action_client import ActionClient  # noqa: E402
from gyodong_agent.config import get_settings  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes-reset-practice-data", action="store_true")
    a = ap.parse_args()
    if not a.yes_reset_practice_data:
        sys.exit("확인 플래그 --yes-reset-practice-data 가 필요합니다")
    s = get_settings()
    c = ActionClient(s.action_base_url, s.action_token)
    r = await c.admin_reset_my_data("RESET-PRACTICE-DATA")
    print("reset ->", r.status, r.error_code or "", r.error_message or "")
    await c.aclose()


if __name__ == "__main__":
    asyncio.run(main())
