"""터미널에서 에이전트와 대화(실제 LLM·Action API 사용). 카카오 없이 공개 TC를 연습할 때 쓴다.

  python3 scripts/cli_chat.py --tc PUB-TC-001
  첫 입력 예: "[인입 계정] 명의: 홍길동 / 연락처: 010-1111-2222\n수박이 안 달아요"
  여러 줄 입력은 줄 끝에 '\\' 를 붙인다. /new 로 새 대화, /quit 로 종료.
"""
import argparse
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gyodong_agent.action_client import ActionClient  # noqa: E402
from gyodong_agent.agent import Agent  # noqa: E402
from gyodong_agent.config import get_settings  # noqa: E402
from gyodong_agent.llm import LLM  # noqa: E402
from gyodong_agent.session import SessionStore  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tc", default="", help="TC ID (대화 첫 줄에 자동으로 붙임)")
    args = ap.parse_args()
    s = get_settings()
    store = SessionStore(":memory:")
    client = ActionClient(s.action_base_url, s.action_token, timeout=s.action_timeout)
    llm = LLM(s.llm_base_url, s.llm_model, s.llm_api_key, s.llm_timeout, s.llm_max_tokens, s.llm_temperature,
              s.llm_enable_thinking)
    agent = Agent(s, client, store, llm)
    conv = uuid.uuid4().hex[:8]
    first = True
    while True:
        lines = []
        prompt = "고객> "
        while True:
            line = input(prompt)
            if line.endswith("\\"):
                lines.append(line[:-1])
                prompt = "...> "
                continue
            lines.append(line)
            break
        text = "\n".join(lines).strip()
        if text == "/quit":
            break
        if text == "/new":
            conv, first = uuid.uuid4().hex[:8], True
            continue
        if first and args.tc:
            text = f"TC ID: {args.tc}\n{text}"
        first = False
        r = await agent.handle(conv, text)
        print(f"\n봇({len(r.answer)}자, {r.elapsed_ms}ms, steps={r.steps})> {r.answer}")
        print("  호출:", ", ".join(f"{t['op']}:{t['status']}" for t in r.trace) or "없음",
              "| 접수:", [x["receipt_id"] for x in r.receipts], "| 오류:", r.error, "\n")
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
