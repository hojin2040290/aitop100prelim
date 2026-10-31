"""카카오 SimpleText 1개용 답변 정리: 마크다운 제거, 500자 상한."""
from __future__ import annotations

import re

FALLBACK = ("확인 중 일시적인 문제가 생겨 지금 바로 답변드리지 못했습니다. 같은 내용을 한 번 더 보내 주시면 "
            "이어서 확인하겠습니다. 급한 건은 대표전화 064-000-0000(평일 09:00~17:00)으로도 접수됩니다.")


def clean(text: str) -> str:
    t = text or ""
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*•]\s+", "· ", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def limit(text: str, n: int = 500) -> str:
    t = clean(text)
    if len(t) <= n:
        return t
    cut = t[:n]
    # 문장 경계에서 자른다
    idx = max(cut.rfind("다."), cut.rfind("요."), cut.rfind("니다."), cut.rfind("\n"))
    if idx >= int(n * 0.6):
        return cut[:idx + 2].rstrip() if cut[idx:idx + 2] in ("다.", "요.") else cut[:idx + 1].rstrip()
    return cut[: n - 1].rstrip() + "…"


def skill_response(text: str) -> dict:
    return {"version": "2.0", "template": {"outputs": [{"simpleText": {"text": text}}]}}
