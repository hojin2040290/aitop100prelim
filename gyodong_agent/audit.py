"""감사 로그(JSONL). 토큰·전화번호·주소를 남기지 않고 사용자 키는 해시로 가명 처리한다."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time

_lock = threading.Lock()
PHONE = re.compile(r"01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}")


def pseudo(key: str | None) -> str:
    return hashlib.sha256((key or "").encode()).hexdigest()[:12] if key else ""


def scrub(text: str | None, n: int = 600) -> str:
    t = PHONE.sub("010-****-****", text or "")
    t = re.sub(r"aitop100_[A-Za-z0-9_-]+", "aitop100_***", t)
    return t[:n]


def write(path: str, row: dict) -> None:
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **row}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with _lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
