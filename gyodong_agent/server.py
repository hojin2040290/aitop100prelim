"""FastAPI 서버: 카카오 웹훅(DISPATCH) → 즉시 2xx → 백그라운드 처리 → /v1/bot/callback 으로 SimpleText 1개.

- 오픈빌더 스킬 형식(userRequest.callbackUrl)도 받아 useCallback 으로 처리한다.
- /chat 은 로컬 검증용(ADMIN_TOKEN 헤더 필요), /health 는 상태 확인.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from . import audit
from .action_client import ActionClient
from .agent import Agent
from .config import get_settings
from .llm import LLM
from .security import RATE_LIMITED_REPLY, ConversationRateLimiter
from .session import SessionStore
from .text_out import FALLBACK, skill_response

log = logging.getLogger("gyodong.server")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

S = get_settings()
AUDIT_PATH = os.environ.get("AUDIT_LOG", "data/audit.jsonl")
RATE = ConversationRateLimiter(int(os.environ.get("CONV_MAX_PER_MIN", "8")), 60.0)
STATE: dict = {"started": time.time(), "handled": 0, "callback_ok": 0, "callback_fail": 0, "latencies": []}


def first(obj, *paths):
    for p in paths:
        cur = obj
        for key in p.split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                cur = None
                break
        if cur not in (None, ""):
            return cur
    return None


def parse_dispatch(payload: dict) -> dict:
    d = payload.get("d") if isinstance(payload.get("d"), dict) else {}
    text = first(d, "content", "text", "utterance", "message.content", "message.text", "message.utterance",
                 "message", "userRequest.utterance")
    if isinstance(text, dict):
        text = None
    return {
        "op": payload.get("op"),
        "callback_token": d.get("callbackToken"),
        "user_key": first(d, "botUserKey", "userKey", "user.botUserKey", "user.id", "author.botUserKey", "author.id",
                          "sender.botUserKey", "sender.id"),
        "group_key": first(d, "botGroupKey", "groupKey", "chat.botGroupKey", "room.botGroupKey", "chatId"),
        "event_id": first(d, "id", "eventId", "messageId", "msgId") or (
            hashlib.sha256(str(d.get("callbackToken")).encode()).hexdigest()[:24] if d.get("callbackToken") else None),
        "text": str(text).strip() if text else None,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = SessionStore(S.db_path, S.session_ttl_sec)
    client = ActionClient(S.action_base_url, S.action_token, timeout=S.action_timeout, rate_per_minute=S.rate_per_minute)
    llm = LLM(S.llm_base_url, S.llm_model, S.llm_api_key, S.llm_timeout, S.llm_max_tokens, S.llm_temperature,
              S.llm_enable_thinking)
    app.state.store, app.state.client = store, client
    app.state.agent = Agent(S, client, store, llm)
    app.state.http = httpx.AsyncClient(timeout=15)
    yield
    await client.aclose()
    await app.state.http.aclose()


app = FastAPI(lifespan=lifespan)


async def _run_agent(conv_key: str, text: str) -> tuple[str, dict]:
    if not RATE.allow(conv_key):
        return RATE_LIMITED_REPLY, {"flags": ["conv_rate_limited"]}
    try:
        r = await asyncio.wait_for(app.state.agent.handle(conv_key, text), timeout=S.total_deadline_sec + 5)
        meta = {"tc": r.tc_id, "steps": r.steps, "ms": r.elapsed_ms, "receipts": [x.get("receipt_id") for x in r.receipts],
                "ops": [t["op"] + ":" + str(t["status"]) + (":" + t["code"] if t.get("code") else "") for t in r.trace], "error": r.error, "flags": r.flags}
        return r.answer, meta
    except Exception as e:
        log.exception("agent failed")
        return FALLBACK, {"error": f"{type(e).__name__}: {e}"}


async def _kakao_callback(callback_token: str, text: str) -> tuple[int | None, str]:
    for attempt in range(3):
        try:
            r = await app.state.http.post(
                f"{S.kakao_api_base}/v1/bot/callback",
                headers={"Authorization": f"KakaoAK {S.kakao_bot_token}", "X-Bot-Callback-Token": callback_token,
                         "Content-Type": "application/json"},
                json={"skillResponse": skill_response(text)})
            if r.status_code < 500:
                return r.status_code, r.text[:300]
        except httpx.HTTPError as e:
            if attempt == 2:
                return None, type(e).__name__
        await asyncio.sleep(0.5 * (attempt + 1))
    return None, "callback retries exhausted"


async def _handle_dispatch(ev: dict) -> None:
    t0 = time.time()
    conv = ev["group_key"] or ev["user_key"] or "unknown"
    if ev["text"]:
        answer, meta = await _run_agent(conv, ev["text"])
    else:
        answer, meta = "안녕하세요, 교동마을 산지직송 상담 채널입니다. 문의 내용을 남겨 주세요.", {}
    status, body = await _kakao_callback(ev["callback_token"], answer)
    ms = int((time.time() - t0) * 1000)
    STATE["handled"] += 1
    STATE["callback_ok" if status and status < 300 else "callback_fail"] += 1
    STATE["latencies"] = (STATE["latencies"] + [ms])[-500:]
    audit.write(AUDIT_PATH, {"kind": "dispatch", "conv": audit.pseudo(conv), "q": audit.scrub(ev["text"]),
                             "a": audit.scrub(answer), "a_len": len(answer), "cb": status, "cb_body": body[:120],
                             "ms": ms, **meta})


async def _handle_skill_callback(conv: str, text: str, callback_url: str) -> None:
    t0 = time.time()
    answer, meta = await _run_agent(conv, text)
    status = None
    try:
        r = await app.state.http.post(callback_url, json=skill_response(answer))
        status = r.status_code
    except httpx.HTTPError as e:
        meta["cb_error"] = type(e).__name__
    audit.write(AUDIT_PATH, {"kind": "skill", "conv": audit.pseudo(conv), "q": audit.scrub(text), "a": audit.scrub(answer),
                             "a_len": len(answer), "cb": status, "ms": int((time.time() - t0) * 1000), **meta})


async def _llm_alive() -> bool | None:
    """모델 서버 /models 확인(10초 캐시)."""
    now = time.time()
    c = STATE.get("llm_check")
    if c and now - c[0] < 10:
        return c[1]
    ok = None
    try:
        r = await app.state.http.get(S.llm_base_url.rstrip("/") + "/models", timeout=2,
                                     headers={"Authorization": f"Bearer {S.llm_api_key}"})
        ok = r.status_code == 200
    except httpx.HTTPError:
        ok = False
    STATE["llm_check"] = (now, ok)
    return ok


@app.get("/")
@app.get("/health")
async def health():
    lat = sorted(STATE["latencies"])
    p95 = lat[int(len(lat) * 0.95) - 1] if lat else None
    return {"ok": True, "uptime_s": int(time.time() - STATE["started"]), "handled": STATE["handled"],
            "callback_ok": STATE["callback_ok"], "callback_fail": STATE["callback_fail"], "p95_ms": p95,
            "llm_model": S.llm_model, "llm_alive": await _llm_alive(), "kakao_token_set": bool(S.kakao_bot_token), "action_token_set": bool(S.action_token),
            "api_calls_total": app.state.store.get_counter("api_calls_total")}


@app.post("/kakao/webhook")
async def webhook(request: Request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("not an object")
    except Exception:
        return JSONResponse({"ok": True})
    # 오픈빌더 스킬 형식
    ur = payload.get("userRequest")
    if isinstance(ur, dict):
        text = str(ur.get("utterance") or "").strip()
        conv = first(ur, "user.id", "user.properties.botUserKey") or "unknown"
        cb = ur.get("callbackUrl")
        if cb:
            asyncio.create_task(_handle_skill_callback(conv, text, cb))
            return JSONResponse({"version": "2.0", "useCallback": True})
        answer, _ = await _run_agent(conv, text)
        return JSONResponse(skill_response(answer))
    ev = parse_dispatch(payload)
    if not ev["callback_token"]:
        return JSONResponse({"ok": True})
    if app.state.store.seen_event(ev["event_id"]):
        return JSONResponse({"ok": True, "duplicate": True})
    asyncio.create_task(_handle_dispatch(ev))  # 1초 안에 2xx 먼저
    return JSONResponse({"ok": True})


@app.post("/chat")
async def chat(request: Request, x_admin_token: str | None = Header(default=None)):
    """로컬 검증용: {"conversation_id": "...", "text": "..."} → 답변. ADMIN_TOKEN 이 필요하다."""
    want = os.environ.get("ADMIN_TOKEN", "")
    if not want or x_admin_token != want:
        raise HTTPException(403, "ADMIN_TOKEN 필요")
    body = await request.json()
    conv = str(body.get("conversation_id") or "local")
    answer, meta = await _run_agent(conv, str(body.get("text") or ""))
    return {"answer": answer, "chars": len(answer), **meta}


def main() -> None:
    import uvicorn
    if not S.kakao_bot_token:
        log.warning("KAKAO_BOT_TOKEN 이 비어 있음 — 카카오 콜백이 실패한다")
    if not S.action_token:
        log.warning("ACTION_TOKEN 이 비어 있음 — Action API 호출이 401 로 실패한다")
    uvicorn.run(app, host=S.bot_host, port=S.bot_port, log_level="warning")


if __name__ == "__main__":
    main()
