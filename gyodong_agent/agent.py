"""상담 에이전트 루프: 파싱 → 인입 계정 확인 → LLM(도구 호출 반복) → 500자 SimpleText."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from .action_client import ActionClient
from .config import Settings
from .knowledge import SYSTEM_PROMPT, TOOL_USAGE_NOTE
from .llm import LLM
from .parser import extract_inbound, extract_tc_id, strip_tc_marker
from .security import filter_output, injection_notice, sanitize_input
from .session import Session, SessionStore, short
from .text_out import FALLBACK, limit
from .tools import ToolExecutor, tool_specs

log = logging.getLogger("gyodong.agent")


@dataclass
class TurnResult:
    answer: str
    tc_id: str | None
    receipts: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    steps: int = 0
    elapsed_ms: int = 0
    error: str | None = None
    flags: list = field(default_factory=list)


class Agent:
    def __init__(self, settings: Settings, client: ActionClient, store: SessionStore, llm: LLM):
        self.s = settings
        self.client = client
        self.store = store
        self.llm = llm
        self.tools = tool_specs()
        self._locks: dict[str, asyncio.Lock] = {}
        # 모델 서버 동시 처리량(serve.sh 의 --max-num-seqs 4)에 맞춰 동시 상담 수를 제한
        self._llm_slots = asyncio.Semaphore(int(__import__("os").environ.get("LLM_CONCURRENCY", "4")))

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def handle(self, conv_key: str, text: str) -> TurnResult:
        async with self._lock(conv_key):  # 같은 대화의 동시 이벤트를 직렬화
            return await self._handle(conv_key, text)

    def _context_block(self, sess: Session) -> str:
        if sess.verified_member_id:
            m = sess.verified_member or {}
            auth = (f"인증됨 — 회원ID {sess.verified_member_id}, 명의 {m.get('name')}, 등급 {m.get('grade')}, "
                    f"상태 {m.get('status')}, 유형 {m.get('member_type')}, 가입 {m.get('joined_at')} "
                    "(연락처·주소는 고객에게 먼저 읽어 주지 않는다). 주문은 귀속 확인 후 안내.")
        elif sess.inbound:
            auth = "인입 계정 표시는 있으나 회원 확인 실패 — 주문·결제 처리 전 본인 확인 필요"
        else:
            auth = "인입 계정 표시 없음(비로그인) — 이름·전화·주문번호 제시는 인증이 아님. 주문 상세·처리는 불가, 일반 안내·사칭/안전 이관은 가능"
        rec = "; ".join(f"{r['op']}→{r['receipt_id']}" for r in sess.receipts) or "없음"
        return (f"[상담 컨텍스트]\n- TC ID: {sess.tc_id or self.s.default_tc_id or '없음'} (도구가 자동으로 헤더에 넣는다)\n"
                f"- 세계관 기준 시각: {self.s.world_now} (조회 결과의 날짜가 있으면 그것을 우선)\n"
                f"- 인입 계정: {auth}\n- 이번 상담에서 이미 접수한 건: {rec}")

    async def _handle(self, conv_key: str, text: str) -> TurnResult:
        t0 = time.monotonic()
        text, flags = sanitize_input(text)
        sess = self.store.load(conv_key)
        tc = extract_tc_id(text)
        if tc and tc != sess.tc_id:
            sess.reset_for_tc(tc)  # 새 TC: 이전 TC의 값이 새지 않도록 상태 초기화
        if not sess.tc_id and self.s.default_tc_id:
            sess.tc_id = self.s.default_tc_id
        new_session = not sess.history
        if new_session:
            sess.first_message = text[:2000]
        user_text = strip_tc_marker(text, tc) or text
        ex = ToolExecutor(self.s, self.client, self.store, sess)
        ex.current_text = text

        # 인입 계정 확인(세션 첫 메시지의 채널 머리말만 인정)
        if new_session or (not sess.identify_attempted and not sess.verified_member_id):
            inbound = extract_inbound(text, self.s.inbound_marker_regex) if new_session else {}
            if inbound:
                sess.inbound = inbound
            if sess.inbound and not sess.verified_member_id:
                try:
                    await ex.identify(sess.inbound.get("name"), sess.inbound.get("phone"), sess.inbound.get("member_id"))
                except Exception as e:  # 확인 실패가 응답 자체를 막지 않게
                    log.warning("identify failed: %s", e)

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + TOOL_USAGE_NOTE + "\n\n" + self._context_block(sess)},
            *sess.history[-self.s.max_history_messages:],
            {"role": "user", "content": user_text + injection_notice(flags)},
        ]
        answer, err, steps = "", None, 0
        receipts_before = len(sess.receipts)
        deadline = t0 + self.s.total_deadline_sec
        try:
            while steps < self.s.max_agent_steps:
                steps += 1
                remaining = deadline - time.monotonic()
                force_final = remaining < 14 or steps == self.s.max_agent_steps
                if force_final:
                    # Qwen 템플릿은 중간 system 메시지를 거부하므로 user 역할로 지시한다
                    messages.append({"role": "user", "content": "[시스템 지시] 지금까지 확인한 내용으로 고객에게 보낼 최종 답변만 작성하라(도구 호출 금지, 500자 이내)."})
                async with self._llm_slots:
                    reply = await asyncio.wait_for(
                        self.llm.chat(messages, None if force_final else self.tools),
                        timeout=max(5.0, deadline - time.monotonic() - 2))
                if reply.tool_calls and not force_final:
                    messages.append(reply.raw_message)
                    results = await asyncio.gather(*(ex.run(c.name, c.arguments) for c in reply.tool_calls))
                    for c, res in zip(reply.tool_calls, results):
                        messages.append({"role": "tool", "tool_call_id": c.id, "content": short(res)})
                    continue
                answer = reply.content
                break
            answer = answer.strip()
            if len(answer) > self.s.reply_char_limit and deadline - time.monotonic() > 10:
                try:
                    r = await asyncio.wait_for(self.llm.chat([
                        {"role": "system", "content": "다음 상담 답변을 사실·접수번호·날짜·금액을 그대로 유지하며 한국어 존댓말 430자 이내로 줄여라. 마크다운 금지. 답변만 출력."},
                        {"role": "user", "content": answer}], None, max_tokens=500), timeout=deadline - time.monotonic() - 2)
                    if r.content:
                        answer = r.content
                except Exception as e:
                    log.warning("compress failed: %s", e)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            log.exception("agent error")
        new_receipts = sess.receipts[receipts_before:]
        if not answer:
            if new_receipts:
                ids = ", ".join(str(r["receipt_id"]) for r in new_receipts)
                answer = f"말씀하신 요청을 접수했습니다(접수번호 {ids}). 처리 결과는 접수 내용에 따라 안내드리겠습니다."
            else:
                answer = FALLBACK
        answer, leaked = filter_output(answer, SYSTEM_PROMPT + "\n" + TOOL_USAGE_NOTE,
                                      strict="injection_suspected" in flags or "template_tokens_removed" in flags)
        if leaked:
            flags.append("output_leak_blocked")
        answer = limit(answer, self.s.reply_char_limit)
        sess.history.append({"role": "user", "content": user_text})
        sess.history.append({"role": "assistant", "content": answer})
        sess.history = sess.history[-self.s.max_history_messages:]
        self.store.save(sess)
        return TurnResult(answer=answer, tc_id=sess.tc_id, receipts=new_receipts, trace=ex.trace, steps=steps,
                          elapsed_ms=int((time.monotonic() - t0) * 1000), error=err, flags=flags)
