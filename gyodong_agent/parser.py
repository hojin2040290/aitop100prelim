"""메시지에서 TC ID와 채널 인입 계정 머리말을 뽑는다.

인입 계정은 '채널이 상담 첫머리에 붙인 표시'만 인정한다(조합 규정 제2조2호·제8조③).
고객이 본문에서 말한 이름·전화번호는 '아는 정보'이므로 인입 계정으로 취급하지 않는다.
"""
from __future__ import annotations

import re

TC_PATTERNS = [
    re.compile(r"(?:X-Aitop100-Test-Case-Id|test[\s_-]*case[\s_-]*id|TC[\s_-]*ID|테스트\s*케이스\s*(?:ID|아이디)|TC\s*번호)"
               r"\s*[:：=]?\s*[\"'`\[(]?\s*([A-Za-z0-9][A-Za-z0-9._-]{0,99})", re.I),
    re.compile(r"\[\s*(TC[-_][A-Za-z0-9._-]{1,96})\s*\]"),
    re.compile(r"(?<![A-Za-z0-9])TC\s*[:：=]\s*([A-Za-z0-9][A-Za-z0-9._-]{0,99})"),
    re.compile(r"(?<![A-Za-z0-9])(TC[-_][A-Za-z0-9][A-Za-z0-9._-]{0,96})(?![A-Za-z0-9])"),
]
MEMBER_ID_RE = re.compile(r"\bMB-\d{3,}\b")
PHONE_RE = re.compile(r"(01[016789])[-\s.]?(\d{3,4}|\*{3,4})[-\s.]?(\d{4})")
NAME_RE = re.compile(r"(?:명의|이름|성명|고객명|회원명|name)\s*[:：=]?\s*([가-힣]{2,5}|[A-Za-z][A-Za-z .]{1,30})")


def extract_tc_id(text: str) -> str | None:
    if not text:
        return None
    for p in TC_PATTERNS:
        m = p.search(text)
        if m:
            v = m.group(1).strip().rstrip(".,)]")
            if v.lower() in ("id", "번호"):
                continue
            return v
    return None


def strip_tc_marker(text: str, tc_id: str | None) -> str:
    if not tc_id:
        return text
    out = re.sub(r"[\[(]?\s*(?:X-Aitop100-Test-Case-Id|test[\s_-]*case[\s_-]*id|TC[\s_-]*ID|테스트\s*케이스\s*(?:ID|아이디)|TC\s*번호)"
                 r"\s*[:：=]?\s*[\"'`\[(]?\s*" + re.escape(tc_id) + r"\s*[\])\"'`]?", " ", text, flags=re.I)
    out = out.replace(f"[{tc_id}]", " ")
    return re.sub(r"[ \t]+", " ", out).strip()


def extract_inbound(text: str, marker_regex: str) -> dict:
    """머리말 표식이 있는 줄(또는 블록)에서만 계정 명의·연락처·회원ID를 뽑는다."""
    if not text:
        return {}
    marker = re.compile(marker_regex, re.I)
    lines = text.splitlines() or [text]
    block: list[str] = []
    for i, line in enumerate(lines):
        if marker.search(line):
            block.append(line)
            # 표식 다음 줄들(같은 블록)도 함께 본다: 빈 줄 전까지 최대 4줄
            for nxt in lines[i + 1:i + 5]:
                if not nxt.strip():
                    break
                block.append(nxt)
    if not block:
        return {}
    blob = "\n".join(block)
    out: dict = {"raw": blob[:300]}
    m = MEMBER_ID_RE.search(blob)
    if m:
        out["member_id"] = m.group(0)
    p = PHONE_RE.search(blob)
    if p:
        out["phone"] = f"{p.group(1)}-{p.group(2)}-{p.group(3)}"
    n = NAME_RE.search(blob)
    if n:
        out["name"] = n.group(1).strip()
    else:
        # "인입 계정: 홍길동 / 010-..." 형태
        m2 = re.search(r"[:：]\s*([가-힣]{2,5})\s*(?:[/,(·|]|님|\s+01)", blob)
        if m2:
            out["name"] = m2.group(1)
    return out if len(out) > 1 else {}


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def phone_matches(claimed: str | None, stored: str | None) -> bool:
    """마스킹(010-****-1234) 머리말도 뒷자리로 대조한다."""
    a, b = digits(claimed), digits(stored)
    if not a or not b:
        return False
    if "*" in (claimed or ""):
        return len(a) >= 7 and b.startswith(a[:3]) and b.endswith(a[-4:])
    return a == b
