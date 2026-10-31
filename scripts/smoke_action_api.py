"""실제 Action API 연결 점검(조회 전용). 공개 TC ID가 필요하다. POST는 하지 않는다.

  python3 scripts/smoke_action_api.py --tc <공개 TC ID>

API 예시 값(actions.json 의 example)으로 GET 몇 개를 호출해 토큰·TC 헤더·응답 형식을 확인한다.
평가 시작 후에는 실행하지 말 것(평가 누적 한도에 포함된다).
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gyodong_agent.action_client import ActionClient  # noqa: E402
from gyodong_agent.api_registry import OPERATIONS  # noqa: E402
from gyodong_agent.config import get_settings  # noqa: E402

CHECK = ["API-01", "API-02", "API-07", "API-10", "API-11", "API-17", "API-18", "API-21"]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tc", required=True)
    args = ap.parse_args()
    s = get_settings()
    if not s.action_token:
        sys.exit("ACTION_TOKEN 이 없습니다(.env)")
    c = ActionClient(s.action_base_url, s.action_token)
    for op_id in CHECK:
        op = OPERATIONS[op_id]
        params = {k: v for k, v in op.example_params.items()}
        if not params:
            continue
        r = await c.call(op_id, args.tc, params)
        print(f"{op_id} {op.method} {op.path} {params} -> {r.status} {r.error_code or ''}")
        if r.ok:
            print("   ", json.dumps(r.data, ensure_ascii=False)[:300])
    await c.aclose()


if __name__ == "__main__":
    asyncio.run(main())
