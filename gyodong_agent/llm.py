"""OpenAI 호환 LLM 클라이언트(vLLM/SGLang/llama.cpp). 네이티브 tool_calls 와
Qwen 계열의 <tool_call>{...}</tool_call> 텍스트 형식을 모두 해석한다."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI, BadRequestError

TOOL_CALL_TAG = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
THINK_TAG = re.compile(r"<think>.*?</think>", re.S)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMReply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: dict | None = None


def _parse_args(s: Any) -> dict:
    if isinstance(s, dict):
        return s
    try:
        v = json.loads(s or "{}")
        return v if isinstance(v, dict) else {}
    except (ValueError, TypeError):
        return {}


class LLM:
    def __init__(self, base_url: str, model: str, api_key: str = "EMPTY", timeout: float = 40.0,
                 max_tokens: int = 700, temperature: float = 0.1, enable_thinking: bool = False):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=1)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.enable_thinking = enable_thinking
        self.native_tools = True

    @staticmethod
    def _inline_tools(messages: list[dict], tools: list[dict]) -> list[dict]:
        spec = json.dumps([t["function"] for t in tools], ensure_ascii=False, separators=(",", ":"))
        note = ("\n\n# Tools\n도구가 필요하면 다른 말 없이 다음 형식으로만 출력한다(여러 개 가능):\n"
                "<tool_call>{\"name\": \"도구이름\", \"arguments\": {...}}</tool_call>\n도구 목록:\n" + spec)
        out = [dict(m) for m in messages]
        if out and out[0].get("role") == "system":
            out[0]["content"] = (out[0].get("content") or "") + note
        # 도구 결과·호출 메시지를 일반 텍스트로 바꿔 템플릿 호환성 확보
        conv = []
        for m in out:
            if m.get("role") == "tool":
                conv.append({"role": "user", "content": f"<tool_response>{m.get('content')}</tool_response>"})
            elif m.get("role") == "assistant" and m.get("tool_calls"):
                txt = "".join(f"<tool_call>{{\"name\": \"{c['function']['name']}\", \"arguments\": {c['function']['arguments']}}}</tool_call>"
                              for c in m["tool_calls"])
                conv.append({"role": "assistant", "content": txt})
            else:
                conv.append(m)
        return conv

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, tool_choice: str = "auto",
                   max_tokens: int | None = None) -> LLMReply:
        kw: dict[str, Any] = dict(model=self.model, messages=messages, temperature=self.temperature,
                                  max_tokens=max_tokens or self.max_tokens,
                                  extra_body={"chat_template_kwargs": {"enable_thinking": self.enable_thinking}})
        if tools and self.native_tools:
            kw["tools"] = tools
            kw["tool_choice"] = tool_choice
        elif tools:
            kw["messages"] = self._inline_tools(messages, tools)
        try:
            r = await self.client.chat.completions.create(**kw)
        except BadRequestError as e:
            # 서버가 --enable-auto-tool-choice 없이 떠 있으면 도구 설명을 프롬프트로 넣는 방식으로 전환
            if tools and self.native_tools and "tool" in str(e).lower():
                self.native_tools = False
                kw.pop("tools", None)
                kw.pop("tool_choice", None)
                kw["messages"] = self._inline_tools(messages, tools)
                r = await self.client.chat.completions.create(**kw)
            else:
                raise
        msg = r.choices[0].message
        content = THINK_TAG.sub("", msg.content or "").strip()
        calls: list[ToolCall] = []
        for tc in (msg.tool_calls or []):
            calls.append(ToolCall(tc.id or f"call_{uuid.uuid4().hex[:8]}", tc.function.name, _parse_args(tc.function.arguments)))
        if not calls and "<tool_call>" in content:
            for m in TOOL_CALL_TAG.finditer(content):
                d = _parse_args(m.group(1))
                if d.get("name"):
                    calls.append(ToolCall(f"call_{uuid.uuid4().hex[:8]}", d["name"], _parse_args(d.get("arguments", {}))))
            content = TOOL_CALL_TAG.sub("", content).strip()
        raw = {"role": "assistant", "content": content or None}
        if calls:
            raw["tool_calls"] = [{"id": c.id, "type": "function",
                                  "function": {"name": c.name, "arguments": json.dumps(c.arguments, ensure_ascii=False)}}
                                 for c in calls]
        return LLMReply(content=content, tool_calls=calls, raw_message=raw)
