"""2037년 영업일·공휴일 달력 (「영업일·공휴일 달력」 기준일 2037-06-30).

- 영업일: 월~금, 공휴일·대체공휴일 제외.
- 산지 정기 출고: 월·수·금. 그 요일이 공휴일이면 그 회차는 건너뛴다(다음날로 미루지 않음).
- N영업일 기한: 기준일 불산입, 다음 영업일이 1일차, N일차 24:00 마감. 기준일이 휴무면 다음 영업일을 기준일로.
- 컷오프 역산: 결제일 직전 영업일을 1로 세어 거꾸로 N번째 영업일 24:00.
- 역일 기한(하자 7일·청약철회 7일·가격 인하 7일)은 휴일에도 흐른다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

HOLIDAYS_2037: dict[date, str] = {
    date(2037, 5, 6): "공휴일",
    date(2037, 5, 25): "공휴일",
    date(2037, 6, 6): "공휴일(토, 대체 없음)",
    date(2037, 8, 15): "공휴일(토)",
    date(2037, 8, 17): "대체공휴일",
    date(2037, 9, 23): "연휴",
    date(2037, 9, 24): "연휴",
    date(2037, 9, 25): "연휴",
    date(2037, 10, 3): "공휴일(토)",
    date(2037, 10, 5): "대체공휴일",
    date(2037, 10, 9): "공휴일",
    date(2037, 12, 25): "공휴일",
}
WEEKDAY_KO = "월화수목금토일"


def parse_date(s: str | date | datetime) -> date:
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    s = str(s).strip()
    return date.fromisoformat(s[:10])


def fmt(d: date) -> str:
    return f"{d.year}-{d.month:02d}-{d.day:02d}({WEEKDAY_KO[d.weekday()]})"


def fmt_md(d: date) -> str:
    return f"{d.month}월 {d.day}일({WEEKDAY_KO[d.weekday()]})"


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS_2037


def is_ship_day(d: date) -> bool:
    return is_business_day(d) and d.weekday() in (0, 2, 4)


def next_business_day(d: date) -> date:
    d = d + timedelta(days=1)
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def add_business_days(start: date, n: int) -> date:
    """접수일(start) 불산입, 다음 영업일이 1일차, N일차를 반환(그날 24:00 마감)."""
    base = start
    if not is_business_day(base):
        # 휴무일 접수는 다음 영업일 접수로 기산
        base = next_business_day(base)
    d = base
    for _ in range(n):
        d = next_business_day(d)
    return d


def cutoff_before(payment_date: date, n: int = 3) -> date:
    """결제일 직전 영업일을 1로 세어 거꾸로 N번째 영업일(그날 24:00이 컷오프)."""
    d = payment_date
    count = 0
    while count < n:
        d -= timedelta(days=1)
        if is_business_day(d):
            count += 1
    return d


def next_ship_days(after: date, count: int = 3) -> list[date]:
    out, d = [], after
    while len(out) < count:
        d += timedelta(days=1)
        if is_ship_day(d):
            out.append(d)
    return out


def calendar_days_between(a: date, b: date) -> int:
    return (b - a).days
