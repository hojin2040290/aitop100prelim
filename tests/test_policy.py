from datetime import date

from gyodong_agent import calendar2037 as cal
from gyodong_agent import policy


def test_business_deadline_examples_from_calendar():
    # 영업일 달력 §4 예시
    assert cal.add_business_days(date(2037, 7, 20), 3) == date(2037, 7, 23)
    assert cal.add_business_days(date(2037, 7, 24), 3) == date(2037, 7, 29)
    assert cal.add_business_days(date(2037, 8, 14), 3) == date(2037, 8, 20)
    assert cal.add_business_days(date(2037, 9, 22), 3) == date(2037, 9, 30)
    # 에스컬레이션 절차서 예시: 06-30 접수 → 07-03(금)
    assert cal.add_business_days(date(2037, 6, 30), 3) == date(2037, 7, 3)
    # 휴무일 접수는 다음 영업일 기산
    assert cal.add_business_days(date(2037, 7, 4), 3) == date(2037, 7, 9)


def test_subscription_cutoffs_from_calendar():
    for pay, cut in [((7, 29), (7, 24)), ((8, 19), (8, 13)), ((9, 30), (9, 22)), ((10, 7), (10, 1)), ((12, 28), (12, 22))]:
        assert cal.cutoff_before(date(2037, *pay), 3) == date(2037, *cut)
    r = policy.subscription_cutoff("2037-09-30", "2037-09-22T23:59")
    assert r["before_cutoff"] and r["cutoff"].startswith("2037-09-22")
    r = policy.subscription_cutoff("2037-09-30", "2037-09-23T00:00")
    assert not r["before_cutoff"] and r["alternatives_if_after_cutoff"]


def test_ship_days_skip_holidays():
    assert not cal.is_ship_day(date(2037, 8, 17))
    assert cal.next_ship_days(date(2037, 8, 14), 1) == [date(2037, 8, 19)]
    assert cal.next_ship_days(date(2037, 9, 21), 1) == [date(2037, 9, 28)]


def test_defect_track_table():
    a = policy.defect_report_track("2037-06-24", "2037-06-30")
    assert a["within_limit"] and a["limit_days"] == 7 and a["elapsed_calendar_days"] == 6
    b = policy.defect_report_track("2037-06-24", "2037-07-05")
    assert not b["within_limit"] and "확인 절차" in b["track"] and "거절" in b["track"]
    c = policy.defect_report_track("2037-06-24", "2037-06-26")
    assert c["within_limit"] and c["limit_days"] == 3
    # 6/28 이후 신고는 6/28 이전 수령분도 7일
    d = policy.defect_report_track("2037-06-22", "2037-06-28")
    assert d["within_limit"] and d["limit_days"] == 7


def test_price_drop_versions_and_coupon():
    old = policy.price_drop_compensation("2037-06-14", 30000, 27000)
    assert "구판" in old["version"]
    new = policy.price_drop_compensation("2037-06-15", 30000, 27000, "2037-06-20", True)
    assert new["difference"] == 3000 and new["coupon"] == "CARE3000"
    new2 = policy.price_drop_compensation("2037-06-20", 30000, 26500, "2037-06-25", True)
    assert new2["coupon"] == "CARE5000"
    late = policy.price_drop_compensation("2037-06-15", 30000, 27000, "2037-06-23", True)
    assert "7역일" in late["decision"]
    neg = policy.price_drop_compensation("2037-06-20", 25000, 27000, "2037-06-21", True)
    assert "0 이하" in neg["decision"]
    promo = policy.price_drop_compensation("2037-06-20", 30000, 25500, "2037-06-21", False, True)
    assert "프로모션" in promo["decision"]
    once = policy.price_drop_compensation("2037-06-20", 30000, 27000, "2037-06-21", True, already_compensated=True)
    assert "1회" in once["decision"]
    unknown = policy.price_drop_compensation("2037-06-20", 30000, 27000, "2037-06-21", None)
    assert "보류" in unknown["decision"]


def test_weight_rules():
    w = policy.weight_check("8kg 이상", 7.6)
    assert w["below_standard"]  # ±5% 적용 금지
    assert not policy.weight_check("8kg 이상", 8.0)["below_standard"]
    assert not policy.weight_check("2kg", 1.92)["below_standard"]  # 정량 ±5%
    assert policy.weight_check("2kg", 1.89)["below_standard"]
    sea = policy.weight_check("1kg", 0.93, seafood=True)
    assert not sea["below_standard"]
    sea2 = policy.weight_check("1kg", 0.90, seafood=True, shipped_kg=1.02, paid_amount=40000)
    assert sea2["below_standard"] and sea2["shortfall_refund_estimate"] == 4000


def test_promo_validity_boundary():
    assert policy.promo_validity("2037-06-26", "2037-07-03", "2037-07-03T23:59")["valid_at_payment"]
    assert not policy.promo_validity("2037-06-26", "2037-07-03", "2037-07-04T00:00")["valid_at_payment"]
