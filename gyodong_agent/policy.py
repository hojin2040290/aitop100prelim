"""결정적 정책 계산기 — LLM이 날짜·금액을 '추정'하지 않도록 도구로 제공한다.

모든 함수는 근거 조문을 함께 돌려준다. 원문에 없는 산식(부분환불 박스 비율 임계 등)은 만들지 않는다.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import ROUND_FLOOR, Decimal

from .calendar2037 import (HOLIDAYS_2037, add_business_days, cutoff_before, fmt, is_business_day, is_ship_day,
                           next_ship_days, parse_date)

DEFECT_REVISION_DATE = date(2037, 6, 28)      # 판매·환불 규정 제20조 3일→7일, 신고 시점 기준
PRICE_DROP_REVISION_DATE = date(2037, 6, 15)  # 조합 규정 제6조② 개정, 주문 시점 기준
CARE_COUPONS = [("CARE3000", 3000), ("CARE5000", 5000), ("CARE10000", 10000)]
BOT_DISCRETION_LIMIT = 50000                  # 권한 위임표 제4조① 건당 5만원(실결제액 기준, 동일 주문·사안 합산)


def _dt(s: str | datetime) -> datetime:
    if isinstance(s, datetime):
        return s
    s = str(s).strip().replace("Z", "+00:00")
    if len(s) == 10:
        return datetime.combine(date.fromisoformat(s), time(0, 0))
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        d = datetime.fromisoformat(s[:19])
    return d.replace(tzinfo=None)


def defect_report_track(received_date: str, report_date: str) -> dict:
    """하자 접수 기한 판정. 적용 판은 '신고(접수) 시점' 기준(개정 이력 제7조)."""
    rcv, rep = parse_date(received_date), parse_date(report_date)
    elapsed = (rep - rcv).days
    if rep >= DEFECT_REVISION_DATE:
        version, limit = "개정판(2037-06-28 시행, 수령일부터 7일)", 7
    else:
        version, limit = "구판(2037-03-02~06-27, 수령일부터 3일)", 3
    within = 0 <= elapsed <= limit
    return {
        "received": fmt(rcv), "reported": fmt(rep), "elapsed_calendar_days": elapsed,
        "applied_version": version, "limit_days": limit, "within_limit": within,
        "track": "즉시처리 트랙(사진·기록으로 하자 확인 시 재배송/전액환불 고객 선택)" if within
        else "기한 경과 — 거절·각하 금지, 확인 절차 트랙으로 접수하고 사유 설명(개정 이력 제8조)",
        "notes": [
            "역일 기준(연휴에도 흐름). 구판 3일 인쇄물/박스 안내문이 있어도 6/28 이후 접수는 7일 적용",
            "사진이 없거나 이미 폐기했어도 접수 거절 금지. 동일 로트 귀책 확정이면 개별 사진 불요",
            "기한은 권리 소멸 기한이 아님",
        ],
        "basis": "판매·환불 규정 제20조·부칙②③, 규정·대응방안 개정 이력 제6~8조",
    }


def business_deadline(start_date: str, n_business_days: int = 3) -> dict:
    """이관 회신 기한 등 N영업일 기한(접수일 불산입, N일차 24:00)."""
    s = parse_date(start_date)
    d = add_business_days(s, int(n_business_days))
    return {"start": fmt(s), "n": int(n_business_days), "deadline": fmt(d) + " 24:00",
            "deadline_date": d.isoformat(), "basis": "에스컬레이션 절차서 제13조, 영업일 달력 §4"}


def subscription_cutoff(payment_date: str, request_datetime: str) -> dict:
    """정기배송 컷오프 = 회차 결제일 3영업일 전 24:00 (결제일 불산입)."""
    pay = parse_date(payment_date)
    cut_day = cutoff_before(pay, 3)
    cut_end = datetime.combine(cut_day + timedelta(days=1), time(0, 0))
    req = _dt(request_datetime)
    before = req < cut_end
    return {
        "payment_date": fmt(pay), "cutoff": fmt(cut_day) + " 24:00", "cutoff_date": cut_day.isoformat(),
        "request_at": req.isoformat(sep=" ", timespec="minutes"), "before_cutoff": before,
        "reflects": "이번 회차부터 반영" if before else "다음 회차부터 반영(이번 회차는 확정·준비 단계)",
        "alternatives_if_after_cutoff": [] if before else [
            "수령일 조정(집하 전)", "배송지 변경(집하 전)", "이번 회차 취소·환불(출고 준비 전에 한함)", "다음 회차 스킵 예약(상시)"],
        "rules": ["스킵 횟수·연속 한도 없음", "해지 위약금 없음·남은 회차 전액환불·이용 회차 할인 소급 반환 없음",
                  "해지 사유 요구·만류 혜택 반복·서면/통화 요구 금지", "컷오프는 날짜와 시각으로 안내"],
        "basis": "정기배송 약관 제3·5·6·7·9·11조, 영업일 달력 §5",
    }


def price_drop_compensation(order_date: str, paid_unit_amount: int, new_normal_price: int | None,
                            drop_date: str | None = None, normal_price_drop_confirmed: bool | None = None,
                            limited_promo_only: bool | None = None, already_compensated: bool = False) -> dict:
    """구매 후 가격 인하 차액 보상(조합 규정 제6조, 개정 이력 제9·10조). 주문 시점으로 판 선택."""
    od = parse_date(order_date)
    out: dict = {"order_date": fmt(od), "basis": "조합 규정 제6조·부칙③, 개정 이력 제9·10조, 권한 위임표 제5조"}
    if od < PRICE_DROP_REVISION_DATE:
        out.update({
            "version": "구판 대응 방안(2037-06-14 이전 결제 주문)",
            "decision": "구판 재량 — 상담사 재량으로 조정(차액 부분환불(현금) 포함 가능), 권한 위임표 재량 한도(건당 5만원) 내",
            "note": "6/15 이후 주문이면 개정판(7일·동일 SKU·쿠폰). 구판 재량을 현행 주문에 적용 금지"})
        if new_normal_price is not None:
            out["difference"] = int(paid_unit_amount) - int(new_normal_price)
        return out
    out["version"] = "개정판(2037-06-15 이후 주문) — 7역일·동일 SKU 정상가 인하·보상 쿠폰"
    if already_compensated:
        out["decision"] = "대상 아님 — 동일 주문·동일 SKU 보상은 1회 한정(이미 보상 기록 있음)"
        return out
    if normal_price_drop_confirmed is False or (limited_promo_only and not normal_price_drop_confirmed):
        out["decision"] = "대상 아님 — 한정 프로모션가(공동구매·타임세일 등)로의 인하는 제외. 확인한 사실과 사유를 함께 안내"
        return out
    if normal_price_drop_confirmed is None:
        out["decision"] = ("확정 보류 — 정상가 변경 이력(가격 정책 시트)과 프로모션 등록 기록 두 축이 확인되지 않음. "
                           "인상만으로 판단 금지. 확인한 사실을 안내하고 필요 시 LANE2_HANDOFF(OPS) 이관")
    if drop_date:
        dd = parse_date(drop_date)
        days = (dd - od).days
        out["days_after_purchase"] = days
        if days > 7 or days < 0:
            out["decision"] = "대상 아님 — 구매 후 7역일 이내 인하가 아님"
            return out
    if new_normal_price is None:
        out.setdefault("decision", "확정 보류 — 인하 후 정상가 확인 필요")
        return out
    diff = int(paid_unit_amount) - int(new_normal_price)
    out["difference"] = diff
    if diff <= 0:
        out["decision"] = "대상 아님 — 실결제액 기준 차액이 0 이하"
        return out
    coupon = next(((c, v) for c, v in CARE_COUPONS if v >= diff), None)
    if coupon:
        out["coupon"] = coupon[0]
        out["coupon_amount"] = coupon[1]
    else:
        out["coupon"] = None
        out["coupon_note"] = "차액이 최대 보상 쿠폰(10,000원) 초과 — 조합 방식 미정, LANE2_HANDOFF(OPS) 이관"
    if normal_price_drop_confirmed:
        out["decision"] = "대상 — 차액 이상 최소 보상 쿠폰 1장(차액 초과분은 정산하지 않음, 현금 환불 아님)"
    return out


_WEIGHT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*kg\s*(이상)?")


def weight_check(listed_weight: str, measured_kg: float, seafood: bool = False,
                 shipped_kg: float | None = None, paid_amount: int | None = None) -> dict:
    """중량 판정. '이상표기'는 절대 하한(오차 없음), '정량표기'는 ±5%, 수산물은 표기 대비 8%(±5%+자연감량3%)."""
    m = _WEIGHT_RE.search(listed_weight or "")
    if not m:
        return {"decision": "표기 중량 형식을 확인할 수 없음 — 상품 원장/라벨 확인 필요"}
    listed = Decimal(m.group(1))
    at_least = bool(m.group(2)) or "이상" in (listed_weight or "")
    meas = Decimal(str(measured_kg))
    short = listed - meas
    rate = (short / listed * 100) if listed else Decimal(0)
    out = {"listed_kg": float(listed), "measured_kg": float(meas), "shortfall_kg": float(max(short, Decimal(0))),
           "shortfall_rate_pct": float(round(rate, 2))}
    if at_least and not seafood:
        out["rule"] = "이상표기 — 표기값이 절대 하한, 허용오차 적용 안 함(상품 원장 §4.2)"
        out["below_standard"] = meas < listed
    elif seafood:
        out["rule"] = "수산물 — 표기 오차 5% + 자연감량 3% = 표기 대비 미달 8% 이내 정상(중량·자연감량 허용치 제7조)"
        out["below_standard"] = rate > 8
        if shipped_kg is not None:
            loss = (Decimal(str(shipped_kg)) - meas) / listed * 100
            out["loss_from_shipped_pct"] = float(round(loss, 2))
            out["mismatch_needs_rephoto"] = loss > 3 and not out["below_standard"]
        if out["below_standard"] and paid_amount:
            refund = (Decimal(paid_amount) * short / listed).to_integral_value(rounding=ROUND_FLOOR)
            out["shortfall_refund_estimate"] = int(refund)
            out["note"] = "8% 초과 시 초과분이 아니라 부족분 전체를 부분환불 또는 재배송(고객 선택), 실결제액 기준"
    else:
        out["rule"] = "정량표기 — ±5% 허용오차(판매·환불 규정 제6조①)"
        out["below_standard"] = rate > 5
    out["evidence_rule"] = "고객 저울 사진 단독 판정 금지 — 출고 실측 기록과 대조, 불일치 시에만 원물·저울·주문번호 한 장 재촬영"
    return out


def promo_validity(valid_from: str, valid_until: str | None, paid_at: str) -> dict:
    """프로모션 유효기간 판정 — 기준 시각은 결제 완료 시각, valid_until 당일 24:00까지 유효."""
    p = _dt(paid_at)
    vf = datetime.combine(parse_date(valid_from), time(0, 0))
    ok = p >= vf
    if valid_until:
        vu_end = datetime.combine(parse_date(valid_until) + timedelta(days=1), time(0, 0))
        ok = ok and p < vu_end
    return {"paid_at": p.isoformat(sep=" ", timespec="minutes"), "valid_from": valid_from,
            "valid_until": (valid_until or "없음") + (" 24:00" if valid_until else ""), "valid_at_payment": ok,
            "basis": "홍보 게시물 상태 기록(기간 판정 기준 = 결제 완료 시각)"}


def calendar_info(day: str) -> dict:
    d = parse_date(day)
    return {"date": fmt(d), "business_day": is_business_day(d), "ship_day": is_ship_day(d),
            "holiday": HOLIDAYS_2037.get(d), "next_ship_days": [fmt(x) for x in next_ship_days(d, 3)]}


def days_between(start: str, end: str) -> dict:
    a, b = parse_date(start), parse_date(end)
    return {"start": fmt(a), "end": fmt(b), "calendar_days": (b - a).days}
