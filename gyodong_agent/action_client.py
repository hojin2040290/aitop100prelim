"""Action API HTTP 클라이언트.

- 모든 업무 호출에 Authorization + X-Aitop100-Test-Case-Id 를 붙인다.
- 60초 슬라이딩 윈도 한도, 평가 누적 한도(3,000) 카운트, TC별 상한.
- 429(시간 창)는 Retry-After 만큼 기다렸다가 제한 재시도, 누적 429 는 재시도하지 않는다.
- 500/503 과 네트워크 오류만 제한적으로 재시도(접수 재전송은 서버가 같은 접수번호를 돌려준다).
- reset 은 이 클래스의 업무 경로(call)로는 호출할 수 없다. 관리자 스크립트 전용 메서드만 존재.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx

from .api_registry import OPERATIONS, RESET_OP_ID, TC_HEADER, TC_PATTERN, Operation, RequestValidationError

log = logging.getLogger("gyodong.action")

CUMULATIVE_LIMIT_MSG = "누적 API 호출 한도를 초과했습니다."


@dataclass
class ApiResult:
    op_id: str
    status: int
    data: Any = None
    error_code: str | None = None
    error_message: str | None = None
    attempts: int = 1
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def summary_for_llm(self) -> dict:
        """LLM에게 줄 결과. 상태 코드의 의미를 사람이 읽을 수 있게 붙인다."""
        if self.ok:
            return {"status": self.status, "data": self.data}
        meaning = {
            400: "요청 형식 오류(파라미터/본문 위반) — 대상이 없다는 뜻이 아님",
            401: "토큰 또는 API 사용 기간 문제 — 시스템 오류",
            403: "접근 권한 없음 — 시스템 오류",
            404: "단건 대상 없음(또는 잘못된 경로)",
            409: "충돌",
            429: "호출 한도 초과",
            500: "일시적 서버 오류",
            503: "일시적 서버 오류",
        }.get(self.status, "오류")
        if self.status == 0:
            meaning = "네트워크 오류 — 결과 미확인"
        return {"status": self.status, "error": meaning, "code": self.error_code, "message": self.error_message}


class BudgetExceeded(RuntimeError):
    pass


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = max(1, per_minute)
        self.calls: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self.lock:
                now = time.monotonic()
                while self.calls and now - self.calls[0] >= 60:
                    self.calls.popleft()
                if len(self.calls) < self.per_minute:
                    self.calls.append(now)
                    return
                wait = 60 - (now - self.calls[0]) + 0.05
            await asyncio.sleep(min(wait, 5))


class ActionClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 10.0, rate_per_minute: int = 95,
                 transport: httpx.AsyncBaseTransport | None = None,
                 on_call: Callable[[str, str, int], Awaitable[None] | None] | None = None,
                 max_retry_after: float = 12.0):
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, transport=transport,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10))
        self.limiter = RateLimiter(rate_per_minute)
        self.on_call = on_call
        self.max_retry_after = max_retry_after
        self.cumulative_exhausted = False
        self.total_calls = 0

    async def aclose(self) -> None:
        await self.client.aclose()

    def _headers(self, tc_id: str | None, need_tc: bool = True) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        if need_tc:
            if not tc_id or not TC_PATTERN.match(tc_id):
                raise RequestValidationError("TC ID가 없거나 형식이 맞지 않아 호출하지 않는다")
            h[TC_HEADER] = tc_id
        return h

    async def call(self, op_id: str, tc_id: str, params: dict | None = None, body: dict | None = None) -> ApiResult:
        if op_id == RESET_OP_ID:
            raise PermissionError("reset 은 상담 경로에서 호출할 수 없다(관리자 스크립트 전용)")
        op = OPERATIONS.get(op_id)
        if op is None:
            raise RequestValidationError(f"등록되지 않은 operation: {op_id}")
        path, query, body_ok = op.build(params, body)
        headers = self._headers(tc_id)
        return await self._send(op, path, query, body_ok, headers, tc_id)

    async def _send(self, op: Operation, path: str, query: dict, body: dict | None, headers: dict,
                    tc_id: str | None) -> ApiResult:
        if self.cumulative_exhausted:
            return ApiResult(op.op_id, 429, error_code="RATE_LIMIT_EXCEEDED", error_message=CUMULATIVE_LIMIT_MSG,
                             attempts=0)
        attempts = 0
        t0 = time.monotonic()
        last: ApiResult | None = None
        while attempts < 3:
            attempts += 1
            await self.limiter.acquire()
            self.total_calls += 1
            try:
                if op.method == "GET":
                    r = await self.client.get(path, params=query, headers=headers)
                else:
                    r = await self.client.post(path, params=query or None, headers=headers,
                                               json=body if body is not None else ({} if not op.is_reset else None))
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = ApiResult(op.op_id, 0, error_code="NETWORK", error_message=type(e).__name__, attempts=attempts)
                await self._notify(op, tc_id, 0)
                await asyncio.sleep(0.4 * attempts)
                continue
            await self._notify(op, tc_id, r.status_code)
            data, code, msg = None, None, None
            if r.content:
                try:
                    data = r.json()
                except ValueError:
                    data = None
            if not (200 <= r.status_code < 300) and isinstance(data, dict):
                code, msg = data.get("code"), data.get("message")
                data = None
            last = ApiResult(op.op_id, r.status_code, data, code, msg, attempts,
                             int((time.monotonic() - t0) * 1000))
            if r.status_code == 429:
                if msg and CUMULATIVE_LIMIT_MSG in msg:
                    self.cumulative_exhausted = True
                    log.error("평가 누적 호출 한도 소진 — 이후 호출 중단")
                    return last
                try:
                    wait = float(r.headers.get("Retry-After", "2"))
                except ValueError:
                    wait = 2.0
                if wait > self.max_retry_after:
                    return last
                await asyncio.sleep(wait)
                continue
            if r.status_code in (500, 503):
                await asyncio.sleep(0.5 * attempts)
                continue
            return last
        return last  # type: ignore[return-value]

    async def _notify(self, op: Operation, tc_id: str | None, status: int) -> None:
        if self.on_call:
            res = self.on_call(op.op_id, tc_id or "", status)
            if asyncio.iscoroutine(res):
                await res

    async def admin_reset_my_data(self, confirm: str) -> ApiResult:
        """연습 데이터 초기화(관리자 전용). 평가 시작 후에는 서버가 409 를 돌려준다."""
        if confirm != "RESET-PRACTICE-DATA":
            raise PermissionError("확인 문자열이 필요하다")
        op = OPERATIONS[RESET_OP_ID]
        headers = self._headers(None, need_tc=False)
        return await self._send(op, op.path, {}, None, headers, None)


def dumps(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))
