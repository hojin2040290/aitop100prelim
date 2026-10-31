import asyncio
import json

import httpx
from openai import AsyncOpenAI

from gyodong_agent.llm import LLM

TOOLS = [{"type": "function", "function": {"name": "API_07", "description": "주문 조회",
                                            "parameters": {"type": "object", "properties": {"order_no": {"type": "string"}}}}}]


def _resp(message):
    return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "qwen",
                                     "choices": [{"index": 0, "message": message, "finish_reason": "stop"}]})


def _llm(handler):
    llm = LLM("http://fake/v1", "qwen")
    llm.client = AsyncOpenAI(base_url="http://fake/v1", api_key="x", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return llm


def test_native_tool_calls():
    def h(req):
        return _resp({"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "API_07", "arguments": "{\"order_no\": \"1\"}"}}]})
    r = asyncio.run(_llm(h).chat([{"role": "user", "content": "hi"}], TOOLS))
    assert r.tool_calls[0].name == "API_07" and r.tool_calls[0].arguments == {"order_no": "1"}


def test_text_tool_call_and_think_strip():
    def h(req):
        return _resp({"role": "assistant", "content": "<think>음</think><tool_call>{\"name\": \"API_07\", \"arguments\": {\"order_no\": \"2\"}}</tool_call>"})
    r = asyncio.run(_llm(h).chat([{"role": "user", "content": "hi"}], TOOLS))
    assert r.tool_calls[0].arguments == {"order_no": "2"} and r.content == ""


def test_fallback_when_server_rejects_tools():
    seen = []

    def h(req):
        body = json.loads(req.content)
        seen.append(body)
        if "tools" in body:
            return httpx.Response(400, json={"error": {"message": "\"auto\" tool choice requires --enable-auto-tool-choice"}})
        return _resp({"role": "assistant", "content": "답변"})
    llm = _llm(h)
    r = asyncio.run(llm.chat([{"role": "system", "content": "S"}, {"role": "user", "content": "hi"}], TOOLS))
    assert r.content == "답변" and not llm.native_tools
    assert "# Tools" in seen[-1]["messages"][0]["content"]
