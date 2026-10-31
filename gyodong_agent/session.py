"""대화 세션 저장소(SQLite, TTL). TC가 바뀌면 상태를 새로 시작해 이전 TC 값이 새지 않게 한다."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Session:
    key: str
    tc_id: str | None = None
    inbound: dict = field(default_factory=dict)          # 채널 머리말에서 파싱한 인입 계정(이름·연락처·회원ID)
    first_message: str = ""
    now: str = ""                                        # 상담 인입 일시(세계관 현재 시각)                              # 세션 첫 메시지(인입 계정 대조용)
    verified_member_id: str | None = None
    verified_member: dict = field(default_factory=dict)  # 내부 대조용(고객에게 읽어 주지 않음)
    identify_attempted: bool = False
    history: list[dict] = field(default_factory=list)    # [{"role":..., "content":...}]
    cache: dict = field(default_factory=dict)            # GET 결과 캐시 "op|json(params)" -> result
    orders: dict = field(default_factory=dict)           # order_no -> 주문 원본(내부)
    owned_orders: dict = field(default_factory=dict)     # order_no -> bool
    payments: dict = field(default_factory=dict)         # approval_no -> 결제 원본(내부)
    shipments: dict = field(default_factory=dict)        # shipment_id -> 배송 원본(내부)
    subscriptions: dict = field(default_factory=dict)
    referred_ids: list = field(default_factory=list)
    known_promos: dict = field(default_factory=dict)     # code -> True/False(존재 여부)
    receipts: list[dict] = field(default_factory=list)   # [{op, target, body, receipt_id, requested_at}]
    api_calls: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def reset_for_tc(self, tc_id: str | None) -> None:
        key = self.key
        self.__dict__.update(Session(key=key, tc_id=tc_id).__dict__)


class SessionStore:
    def __init__(self, path: str, ttl_sec: int = 6 * 3600):
        self.path = path
        self.ttl = ttl_sec
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None
        self._conn.execute("CREATE TABLE IF NOT EXISTS sessions (key TEXT PRIMARY KEY, data TEXT, updated REAL)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, at REAL)")
        self._conn.commit()

    def load(self, key: str) -> Session:
        with self._lock:
            row = self._conn.execute("SELECT data, updated FROM sessions WHERE key=?", (key,)).fetchone()
        if not row or time.time() - row[1] > self.ttl:
            return Session(key=key)
        try:
            d = json.loads(row[0])
            s = Session(key=key)
            for k, v in d.items():
                if hasattr(s, k):
                    setattr(s, k, v)
            return s
        except (ValueError, TypeError):
            return Session(key=key)

    def save(self, s: Session) -> None:
        s.updated_at = time.time()
        data = json.dumps(asdict(s), ensure_ascii=False, default=str)
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO sessions(key, data, updated) VALUES (?,?,?)",
                               (s.key, data, s.updated_at))
            self._conn.execute("DELETE FROM sessions WHERE updated < ?", (time.time() - self.ttl,))
            self._conn.commit()

    def incr(self, name: str, by: int = 1) -> int:
        with self._lock:
            self._conn.execute("INSERT INTO counters(name, value) VALUES(?, 0) ON CONFLICT(name) DO NOTHING", (name,))
            self._conn.execute("UPDATE counters SET value = value + ? WHERE name=?", (by, name))
            v = self._conn.execute("SELECT value FROM counters WHERE name=?", (name,)).fetchone()[0]
            self._conn.commit()
        return int(v)

    def get_counter(self, name: str) -> int:
        with self._lock:
            row = self._conn.execute("SELECT value FROM counters WHERE name=?", (name,)).fetchone()
        return int(row[0]) if row else 0

    def seen_event(self, event_id: str) -> bool:
        """중복 이벤트 제거. 처음 보면 False 를 돌려주고 기록한다."""
        if not event_id:
            return False
        with self._lock:
            try:
                self._conn.execute("INSERT INTO events(event_id, at) VALUES(?,?)", (event_id, time.time()))
                self._conn.execute("DELETE FROM events WHERE at < ?", (time.time() - 3600,))
                self._conn.commit()
                return False
            except sqlite3.IntegrityError:
                return True


def short(o: Any, limit: int = 3500) -> str:
    s = json.dumps(o, ensure_ascii=False, separators=(",", ":"), default=str)
    return s if len(s) <= limit else s[:limit] + "…(생략)"
