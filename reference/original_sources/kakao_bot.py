"""
카카오톡 봇 ↔ vLLM(Qwen3.8-27B) 연결 테스트 서버 (웹훅 방식)

흐름 (카카오 문서 기준):
  1) 사용자가 봇에게 메시지 → 카카오톡 서버가 웹훅 URL로 DISPATCH 이벤트(POST)를 보냄
  2) 이 서버는 1초 안에 200으로 먼저 응답 (문서: "1초 이내에 2xx로 응답")
  3) 뒤에서 vLLM에 답변 생성 → 메시지 콜백 API(/v1/bot/callback)로 답장
     (봇 인증 토큰 + 이벤트의 d.callbackToken, 콜백 토큰은 5분 안에 사용)

실행:
  1) .env 파일에 KAKAO_BOT_TOKEN 입력 (env.example 을 복사해서 만듦)
  2) python kakao_bot.py
  3) bash start_tunnel.sh 로 공개 주소를 만들고, 카카오 디벨로퍼스의 웹훅 URL에
     https://<공개주소>/kakao/webhook 등록

모든 기록은 results/kakao_events.csv 한 파일에 저장됩니다.
"""
import asyncio
import csv
import json
import os
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

try:
    import fcntl
except ImportError:
    fcntl = None

import httpx
import uvicorn
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI


# ---------------------------------------------------------------- 설정 (.env 또는 환경 변수)
def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
BOT_TOKEN = os.environ.get("KAKAO_BOT_TOKEN", "")
KAKAO_API = os.environ.get("KAKAO_API_BASE", "https://kapi.kakao.com").rstrip("/")
VLLM_URL = os.environ.get("VLLM_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "qwen")
PORT = int(os.environ.get("BOT_PORT", "9000"))
# echo: LLM 없이 받은 말을 그대로 돌려줌 (카카오 연결만 확인할 때) / llm: VLLM_URL 의 모델로 답변
BOT_MODE = os.environ.get("BOT_MODE", "llm").strip().lower()
LOG_PATH = os.environ.get("BOT_LOG", os.path.join("results", "kakao_events.csv"))
SYSTEM_PROMPT = os.environ.get(
    "BOT_SYSTEM_PROMPT",
    "너는 카카오톡에서 대화하는 친절한 한국어 AI 도우미야. 답변은 짧고 정확하게, 500자 이내로 해.")
MAX_HISTORY_TURNS = 10        # 사용자별로 기억할 최근 대화 수
LLM_MAX_TOKENS = 800
KAKAO_TEXT_LIMIT = 1000       # SimpleText 최대 1,000자 (500자 넘으면 '전체 보기'로 접힘)

# ---------------------------------------------------------------- CSV 기록 (한 줄마다 디스크 확정)
COLUMNS = [
    "event_id", "received_at", "stage", "event_type", "op", "user_key", "group_key",
    "user_text", "answer", "llm_ms", "callback_status", "callback_response",
    "total_ms", "error", "callback_token_prefix", "raw_payload",
]
_log_lock = threading.Lock()


def log(row):
    with _log_lock:
        folder = os.path.dirname(LOG_PATH)
        if folder:
            os.makedirs(folder, exist_ok=True)
        new = not os.path.exists(LOG_PATH) or os.path.getsize(LOG_PATH) == 0
        with open(LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)
            try:
                w = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL, extrasaction="ignore")
                if new:
                    w.writeheader()
                w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in COLUMNS})
                f.flush()
                os.fsync(f.fileno())
            finally:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------- 이벤트에서 값 꺼내기
# 확인된 것: op=DISPATCH, 콜백 토큰은 d.callbackToken
# 아직 문서로 확인 못 한 것: 이벤트 이름 필드, 메시지 글자 필드, 사용자 키 필드
#   → 흔히 쓰는 이름을 차례로 찾아보고, 원본은 raw_payload 에 전부 남김
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


def parse_event(payload):
    d = payload.get("d") if isinstance(payload.get("d"), dict) else {}
    text = first(d, "content", "text", "utterance", "message.content", "message.text",
                 "message.utterance", "message", "userRequest.utterance")
    if isinstance(text, dict):
        text = None
    return {
        "op": payload.get("op"),
        "event_type": first(payload, "t", "type", "event", "eventType", "d.type", "d.eventType"),
        "callback_token": d.get("callbackToken"),
        "user_key": first(d, "botUserKey", "userKey", "user.botUserKey", "user.id", "author.botUserKey",
                          "author.id", "sender.botUserKey", "sender.id"),
        "group_key": first(d, "botGroupKey", "groupKey", "chat.botGroupKey", "room.botGroupKey", "chatId"),
        "text": str(text).strip() if text else None,
    }


# ---------------------------------------------------------------- vLLM 호출 + 카카오 답장
llm = AsyncOpenAI(base_url=VLLM_URL, api_key="EMPTY", timeout=240, max_retries=1)
http = httpx.AsyncClient(timeout=20)
history = defaultdict(lambda: deque(maxlen=MAX_HISTORY_TURNS * 2))


async def ask_llm(convo_key, text):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, *history[convo_key], {"role": "user", "content": text}]
    r = await llm.chat.completions.create(
        model=VLLM_MODEL, messages=msgs, max_tokens=LLM_MAX_TOKENS, temperature=0.7, top_p=0.8,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    answer = (r.choices[0].message.content or "").strip() or "답변을 만들지 못했어요. 다시 말씀해 주세요."
    history[convo_key].append({"role": "user", "content": text})
    history[convo_key].append({"role": "assistant", "content": answer})
    return answer


def skill_text(text):
    if len(text) > KAKAO_TEXT_LIMIT:
        text = text[:KAKAO_TEXT_LIMIT - 1] + "…"
    return {"version": "2.0", "template": {"outputs": [{"simpleText": {"text": text}}]}}


async def send_callback(callback_token, text):
    r = await http.post(
        f"{KAKAO_API}/v1/bot/callback",
        headers={"Authorization": f"KakaoAK {BOT_TOKEN}", "X-Bot-Callback-Token": callback_token,
                 "Content-Type": "application/json"},
        json={"skillResponse": skill_text(text)})
    return r.status_code, r.text[:500]


async def handle(event_id, received, payload):
    ev = parse_event(payload)
    base = {"event_id": event_id, "received_at": received, "event_type": ev["event_type"], "op": ev["op"],
            "user_key": ev["user_key"], "group_key": ev["group_key"], "user_text": ev["text"],
            "callback_token_prefix": (ev["callback_token"] or "")[:6],
            "raw_payload": json.dumps(payload, ensure_ascii=False)}
    log({**base, "stage": "received"})

    if not ev["callback_token"]:
        log({**base, "stage": "skipped", "error": "callbackToken 없음 (답장할 수 없는 이벤트)"})
        return

    t0 = time.time()
    answer, llm_ms, err = None, None, None
    try:
        if ev["text"] and BOT_MODE == "echo":
            answer = f"[에코] {ev['text']}"
        elif ev["text"]:
            convo = ev["group_key"] or ev["user_key"] or "unknown"
            answer = await ask_llm(convo, ev["text"])
            llm_ms = round((time.time() - t0) * 1000)
        else:  # 입장·초대 같은 이벤트: 인사말
            answer = "안녕하세요! 무엇이든 물어보세요."
    except Exception as e:
        err = f"LLM 오류 {type(e).__name__}: {e}"
        answer = "지금은 답변 서버에 문제가 있어요. 잠시 후 다시 시도해 주세요."

    try:
        status, body = await send_callback(ev["callback_token"], answer)
    except Exception as e:
        status, body = None, None
        err = (err + " / " if err else "") + f"콜백 오류 {type(e).__name__}: {e}"

    log({**base, "stage": "replied", "answer": answer, "llm_ms": llm_ms, "callback_status": status,
         "callback_response": body, "total_ms": round((time.time() - t0) * 1000), "error": err})


# ---------------------------------------------------------------- 웹 서버
app = FastAPI()
_counter = 0


@app.get("/")
async def health():
    return {"ok": True, "model": VLLM_MODEL, "token_set": bool(BOT_TOKEN)}


@app.post("/kakao/webhook")
async def webhook(request: Request, tasks: BackgroundTasks):
    global _counter
    received = datetime.now().isoformat(timespec="milliseconds")
    _counter += 1
    event_id = f"{datetime.now():%H%M%S}-{_counter}"
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("JSON 객체가 아님")
    except Exception as e:
        raw = (await request.body())[:2000].decode("utf-8", "replace")
        tasks.add_task(log, {"event_id": event_id, "received_at": received, "stage": "bad-request",
                             "error": f"{type(e).__name__}: {e}", "raw_payload": raw})
        return JSONResponse({"ok": True})
    # 1초 제한 때문에 먼저 200 응답, 실제 처리는 응답 뒤에 진행
    tasks.add_task(handle, event_id, received, payload)
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    if not BOT_TOKEN:
        sys.exit("KAKAO_BOT_TOKEN 이 비어 있습니다. .env 파일에 봇 인증 토큰을 넣으세요.")
    if BOT_MODE not in ("echo", "llm"):
        sys.exit("BOT_MODE 는 echo 또는 llm 이어야 합니다.")
    mode = "에코 (LLM 사용 안 함)" if BOT_MODE == "echo" else f"LLM ({VLLM_URL}, 모델: {VLLM_MODEL})"
    print(f"카카오 봇 서버 시작: http://127.0.0.1:{PORT}/kakao/webhook  · 답변 방식: {mode}")
    print(f"기록 파일: {LOG_PATH}")
    # 터널(cloudflared)이 같은 컴퓨터에서 접속하므로 외부에 직접 열지 않고 127.0.0.1 에만 엶
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
