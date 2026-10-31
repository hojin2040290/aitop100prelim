import asyncio

import pytest

from gyodong_agent.action_client import ActionClient
from gyodong_agent.agent import Agent
from gyodong_agent.config import Settings
from gyodong_agent.session import Session, SessionStore
from gyodong_agent.tools import ToolExecutor

from .fakes import FakeActionAPI, ScriptedLLM

INBOUND = "[인입 계정] 명의: 홍길동 / 연락처: 010-1111-2222\n"


def run(c):
    return asyncio.get_event_loop().run_until_complete(c) if False else asyncio.run(c)


def make(tc="PUB-TC-1"):
    api = FakeActionAPI()
    s = Settings(action_token="aitop100_test", db_path=":memory:", default_tc_id="")
    client = ActionClient(s.action_base_url, s.action_token, transport=api.transport())
    store = SessionStore(":memory:")
    sess = Session(key="u1", tc_id=tc)
    ex = ToolExecutor(s, client, store, sess)
    # 고객이 대화에서 확인해 준 값(접수 가드용)
    ex.current_text = "주문 100100001, 100100002, 100100003 · 번호 010-1111-2222 · 소득공제용"
    return api, s, client, store, sess, ex


async def _verified(ex):
    r = await ex.identify("홍길동", "010-1111-2222", None)
    assert r["verified"]


def test_identify_and_order_ownership():
    async def go():
        api, s, client, store, sess, ex = make()
        await _verified(ex)
        own = await ex.run("API_07", {"order_no": "100100001"})
        assert own["data"]["order_no"] == "100100001"
        assert "제주 어딘가" not in str(own)  # 저장 주소를 읽어 주지 않음
        other = await ex.run("API_07", {"order_no": "100100002"})
        assert other["access"] == "DENIED" and "김타인" not in str(other)
        missing = await ex.run("API_07", {"order_no": "999"})
        assert missing["status"] == 404
        # TC 헤더가 모든 호출에 붙는다
        assert all(c[4].get("x-aitop100-test-case-id") == "PUB-TC-1" for c in api.calls)
    run(go())


def test_unverified_blocks_order_actions():
    async def go():
        api, s, client, store, sess, ex = make()
        r = await ex.run("API_07", {"order_no": "100100001"})
        assert r["access"] == "UNVERIFIED"
        p = await ex.run("API_29", {"order_no": "100100001", "amount": 27900, "reason": "하자"})
        assert p["blocked"] and not api.posts()
    run(go())


def test_refund_guard_and_duplicate():
    async def go():
        api, s, client, store, sess, ex = make()
        await _verified(ex)
        r = await ex.run("API_29", {"order_no": "100100001", "amount": 27900, "reason": "당도 미달 하자 전액환불"})
        assert r["submitted"] and r["receipt_id"] == "REFUND-001"
        again = await ex.run("API_29", {"order_no": "100100001", "amount": 1000, "reason": "변경"})
        assert again["duplicate"] and len(api.posts()) == 1  # 덮어쓰기 방지
        over = await ex.run("API_29", {"order_no": "100100003", "amount": 60000, "reason": "부분"})
        assert over["blocked"] and "5만원" in over["reason"]
        item = await ex.run("API_29", {"order_no": "100100003", "amount": 90000, "reason": "HGL-STD-10 2박스 하자 전액"})
        assert item["submitted"]
        other = await ex.run("API_29", {"order_no": "100100002", "amount": 24000, "reason": "x"})
        assert other["blocked"]
        bad = await ex.run("API_29", {"order_no": "100100001", "amount": 100, "reason": "x", "account": "123"})
        assert "error" in bad
    run(go())


def test_payment_method_guards():
    async def go():
        api, s, client, store, sess, ex = make()
        await _verified(ex)
        card_cash = await ex.run("API_32", {"approval_no": "PAY-100100001", "receipt_number": "01011112222"})
        assert card_cash["blocked"] and "매출전표" in card_cash["reason"]
        cash = await ex.run("API_32", {"approval_no": "PAY-100100003", "receipt_number": "01011112222"})
        assert cash["submitted"]
        cancel_bank = await ex.run("API_31", {"approval_no": "PAY-100100003"})
        assert cancel_bank["blocked"]
        cancel_card = await ex.run("API_31", {"approval_no": "PAY-100100001"})
        assert cancel_card["submitted"]
    run(go())


def test_coupon_requires_registered_promo_and_own_member():
    async def go():
        api, s, client, store, sess, ex = make()
        await _verified(ex)
        fake = await ex.run("API_33", {"member_id": "MB-1", "promo_code": "VIP99"})
        assert fake["blocked"]
        ok = await ex.run("API_33", {"member_id": "MB-1", "promo_code": "care5000"})
        assert ok["submitted"]
        other = await ex.run("API_33", {"member_id": "MB-2", "promo_code": "CARE5000"})
        assert other["blocked"]
    run(go())


def test_escalation_format_and_deadline():
    async def go():
        api, s, client, store, sess, ex = make()
        r = await ex.run("escalate", {"lane": "LANE2_HANDOFF", "target": "SECURITY", "priority": "긴급",
                                       "reason": "사칭 오픈채팅 결제 유도 제보, 결제 전, 우리 주문 기록 없음"})
        assert r["submitted"] and r["reply_deadline"].startswith("2037-07-03")
        body = api.posts()[0][3]
        assert body["lane"] == "LANE2_HANDOFF" and body["reason"].startswith("[SECURITY][긴급]")
        bad = await ex.run("escalate", {"lane": "LANE2_HANDOFF", "target": "CEO", "priority": "일반", "reason": "x"})
        assert bad["blocked"]
        # F2: 같은 레인·대상이라도 다른 사안(본문)이면 별도 이관
        other = await ex.run("escalate", {"lane": "LANE2_HANDOFF", "target": "SECURITY", "priority": "긴급", "reason": "다른 사안"})
        assert other["submitted"] and other["escalation_id"] != r["escalation_id"]
        dup = await ex.run("escalate", {"lane": "LANE2_HANDOFF", "target": "SECURITY", "priority": "긴급",
                                         "reason": "사칭 오픈채팅 결제 유도 제보, 결제 전, 우리 주문 기록 없음"})
        assert dup["duplicate"] and dup["receipt_id"] == r["escalation_id"]
    run(go())


def test_subscription_and_shipment_guards():
    async def go():
        api, s, client, store, sess, ex = make()
        await _verified(ex)
        r = await ex.run("API_40", {"subscription_id": "SUB-1", "kind": "SKIP"})
        assert r["submitted"]
        rs = await ex.run("API_28", {"shipment_id": "SHP-100100001-01"})
        assert rs["submitted"]
        rc = await ex.run("API_37", {"shipment_id": "SHP-100100001-01", "charge_amount": 0})
        assert rc["blocked"]
    run(go())


def test_reset_cannot_be_called_from_agent_path():
    async def go():
        api, s, client, store, sess, ex = make()
        with pytest.raises(PermissionError):
            await client.call("resetMyActionData", "PUB-TC-1")
        r = await ex.run("resetMyActionData", {})
        assert "error" in r
        assert not api.calls
    run(go())


def test_retry_on_503_then_success_and_404_vs_empty():
    async def go():
        api, s, client, store, sess, ex = make()
        api.fail_next = [503]
        r = await client.call("API-01", "PUB-TC-1", {"sku": "X"})
        assert r.status == 404 and r.attempts == 2
        e = await client.call("API-02", "PUB-TC-1", {"item": "ZZZ"})
        assert e.status == 200 and e.data == []
    run(go())


def test_get_cache_avoids_duplicate_calls():
    async def go():
        api, s, client, store, sess, ex = make()
        await ex.run("API_20", {"code": "CARE5000"})
        await ex.run("API_20", {"code": "CARE5000"})
        assert sum(1 for c in api.calls if c[1] == "/api/promos/CARE5000") == 1
    run(go())


def test_agent_end_to_end_with_scripted_llm():
    async def go():
        api = FakeActionAPI()
        s = Settings(action_token="aitop100_t", db_path=":memory:")
        client = ActionClient(s.action_base_url, s.action_token, transport=api.transport())
        store = SessionStore(":memory:")
        llm = ScriptedLLM([
            [("API_07", {"order_no": "100100001"}), ("API_11", {"order_no": "100100001"})],
            [("API_29", {"order_no": "100100001", "amount": 27900, "reason": "당도 미달 하자 전액환불(고객 선택)"})],
            "**당도 미달**이 확인되어 전액환불 요청을 접수했습니다(접수번호 REFUND-001). 원결제수단으로 처리됩니다.",
        ])
        agent = Agent(s, client, store, llm)
        r = await agent.handle("u1", "TC ID: PUB-TC-9\n" + INBOUND + "수박이 하나도 안 달아요. 환불해 주세요. 주문 100100001")
        assert r.tc_id == "PUB-TC-9"
        assert "REFUND-001" in r.answer and "**" not in r.answer and len(r.answer) <= 500
        assert [x["receipt_id"] for x in r.receipts] == ["REFUND-001"]
        system = llm.seen[0][0]["content"]
        assert "인증됨 — 회원ID MB-1" in system and "PUB-TC-9" not in llm.seen[0][-1]["content"]
        # 새 TC가 오면 세션 초기화(이전 TC 인증·접수 정보가 새지 않음)
        llm.script = ["새 상담입니다."]
        r2 = await agent.handle("u1", "TC ID: PUB-TC-10\n주문 100100001 상태 알려주세요")
        sys2 = llm.seen[-1][0]["content"]
        assert r2.tc_id == "PUB-TC-10" and "인입 계정 표시 없음" in sys2 and "REFUND-001" not in sys2
    run(go())


def test_agent_llm_failure_falls_back_with_receipts():
    async def go():
        api = FakeActionAPI()
        s = Settings(action_token="aitop100_t", db_path=":memory:")
        client = ActionClient(s.action_base_url, s.action_token, transport=api.transport())
        store = SessionStore(":memory:")
        llm = ScriptedLLM([[("escalate", {"lane": "LANE3_CLAIM", "target": "NONE", "priority": "일반", "reason": "병원비 청구"})],
                           RuntimeError("llm down")])
        agent = Agent(s, client, store, llm)
        r = await agent.handle("u2", "TC ID: PUB-TC-3\n수박 먹고 배탈 났어요 병원비 주세요")
        assert "ESC-001" in r.answer and r.error
    run(go())


def test_long_answer_is_limited():
    async def go():
        api = FakeActionAPI()
        s = Settings(action_token="t", db_path=":memory:", total_deadline_sec=5)
        client = ActionClient(s.action_base_url, s.action_token, transport=api.transport())
        agent = Agent(s, client, SessionStore(":memory:"), ScriptedLLM(["가" * 900]))
        r = await agent.handle("u3", "TC ID: X1\n안녕하세요")
        assert len(r.answer) <= 500
    run(go())


def test_set_test_case_id_only_from_message():
    async def go():
        api, s, client, store, sess, ex = make(tc=None)
        ex.current_text = "테스트 케이스는 PUB-77 입니다"
        assert not (await ex.run("set_test_case_id", {"tc_id": "PUB-99"}))["ok"]
        assert (await ex.run("set_test_case_id", {"tc_id": "PUB-77"}))["ok"] and sess.tc_id == "PUB-77"
    run(go())


def test_lenient_mode_only_without_inbound():
    async def go():
        api, s, client, store, sess, ex = make()
        s.auth_mode = "lenient"
        r = await ex.run("API_07", {"order_no": "100100002"})
        assert r["data"]["order_no"] == "100100002"
        # 인입 계정이 표시됐는데 인증이 안 되면 lenient 라도 막는다
        sess.inbound = {"name": "누군가", "phone": "010-0000-0000"}
        sess.orders.clear(); sess.owned_orders.clear()
        r2 = await ex.run("API_29", {"order_no": "100100002", "amount": 1000, "reason": "x"})
        assert r2["blocked"]
    run(go())


def test_arg_type_coercion_from_xml_tool_calls():
    async def go():
        api, s, client, store, sess, ex = make()
        await _verified(ex)
        r = await ex.run("API_29", {"order_no": 100100001, "amount": "27,900", "reason": "하자"})
        assert r["submitted"]
        body = api.posts()[0][3]
        assert body == {"order_no": "100100001", "amount": 27900, "reason": "하자"}
    run(go())


def test_public_tc_L03_address_change_flow():
    from .fakes import MEMBERS, ORDERS, _order
    MEMBERS["MB-SJH"] = {**MEMBERS["MB-1"], "member_id": "MB-SJH", "name": "서지호", "phone": "019-7777-5231"}
    ORDERS["100500007"] = _order("100500007", "MB-SJH", 31900, [{"sku": "WTM-SEL-8", "name": "수박", "qty": 1, "unit_price": 27900}], status="PAID")

    async def go():
        api = FakeActionAPI()
        s = Settings(action_token="aitop100_t", db_path=":memory:")
        client = ActionClient(s.action_base_url, s.action_token, transport=api.transport())
        llm = ScriptedLLM([
            "배송지를 변경할 주문번호를 알려 주시겠어요?",
            [("API_11", {"order_no": "100500007"})],
            "집하 전이라 변경 가능합니다. 동·호수까지 상세주소를 알려 주세요.",
            [("API_24", {"order_no": "100500007", "new_address": "경기 성남시 분당구 정자동 1 101동 1001호"})],
            "요청하신 주소로 배송지 변경 요청을 접수했습니다(접수번호 ORDERS-ADDRESS-CHANGE-REQUESTS-001).",
        ])
        agent = Agent(s, client, SessionStore(":memory:"), llm)
        first = ("case metadata\n- id: L-03\n- 상담 인입 일시: 2037-06-30(화) 15:16\n- 인입창구: 조합몰 1:1 채팅\n"
                 "- 인입 계정: 회원 로그인 · 서지호 · 019-****-5231\n\n주소 잘못 넣었어요. 경기 성남시로 바꿔주세요.")
        r1 = await agent.handle("kakao-u", first)
        assert r1.tc_id == "L-03"
        ctx = llm.seen[0][0]["content"]
        assert "인증됨 — 회원ID MB-SJH" in ctx and "2037-06-30T15:16" in ctx
        r2 = await agent.handle("kakao-u", "100500007 이에요")
        r3 = await agent.handle("kakao-u", "경기 성남시 분당구 정자동 1 101동 1001호")
        assert r3.receipts and r3.tc_id == "L-03"
        assert all(c[4]["x-aitop100-test-case-id"] == "L-03" for c in api.calls)
        posts = api.posts()
        assert len(posts) == 1 and posts[0][1] == "/api/orders/100500007/address-change-requests"
        assert posts[0][3] == {"new_address": "경기 성남시 분당구 정자동 1 101동 1001호"}
    run(go())


def test_identify_system_error_is_not_mismatch_and_retries():
    async def go():
        api = FakeActionAPI()
        s = Settings(action_token="aitop100_t", db_path=":memory:")
        client = ActionClient(s.action_base_url, s.action_token, transport=api.transport())
        llm = ScriptedLLM(["주문번호를 알려 주세요.", "확인했습니다."])
        agent = Agent(s, client, SessionStore(":memory:"), llm)
        api.fail_next = [401]
        await agent.handle("k", "- id: T-1\n- 인입 계정: 회원 로그인 · 홍길동 · 010-****-2222\n주소 바꿔주세요")
        ctx1 = llm.seen[0][0]["content"]
        assert "시스템 조회 오류(401" in ctx1 and "회원 불일치라고 말하지 말 것" in ctx1
        await agent.handle("k", "100100001 입니다")
        assert "인증됨 — 회원ID MB-1" in llm.seen[-1][0]["content"]
    run(go())


def test_L05_regression_no_guessing_before_customer_confirms():
    async def go():
        api, s, client, store, sess, ex = make()
        await _verified(ex)
        ex.current_text = "지난주 주문건 현금영수증 처리 부탁드립니다. 010-1111-2222로 발행해주세요."
        r = await ex.run("API_32", {"approval_no": "PAY-100100003", "receipt_number": "010-1111-2222"})
        assert r["blocked"] and "주문" in r["reason"]
        ex.current_text += " 무통장으로 낸 100100003 건이요"
        r = await ex.run("API_32", {"approval_no": "PAY-100100003", "receipt_number": "010-1111-2222"})
        assert r["blocked"] and "발행 구분" in r["reason"]
        ex.current_text += " 소득공제용으로요"
        r = await ex.run("API_32", {"approval_no": "PAY-100100003", "receipt_number": "01011112222"})
        assert r["submitted"]
        assert not [c for c in api.posts() if "PAY-100100001" in c[1]]
    run(go())


def test_address_must_be_customer_given():
    async def go():
        api, s, client, store, sess, ex = make()
        await _verified(ex)
        r = await ex.run("API_24", {"order_no": "100100001", "new_address": "경기 성남시 분당구 어딘가 1"})
        assert r["blocked"] and not api.posts()
    run(go())


def test_F3_corrected_value_resubmits_but_refund_does_not():
    async def go():
        api, s, client, store, sess, ex = make()
        await _verified(ex)
        ex.current_text += " 주소는 경기 성남시 분당구 정자동 1 101동 1001호"
        a = await ex.run("API_24", {"order_no": "100100001", "new_address": "경기 성남시 분당구 정자동 1 101동 1001호"})
        ex.current_text += " 아 잘못 말했어요 101동 1002호예요"
        same = await ex.run("API_24", {"order_no": "100100001", "new_address": "경기 성남시 분당구 정자동 1 101동 1001호"})
        assert same["duplicate"]
        b = await ex.run("API_24", {"order_no": "100100001", "new_address": "경기 성남시 분당구 정자동 1 101동 1002호"})
        assert b["submitted"] and b["updated_previous"] and b["receipt_id"] == a["receipt_id"]
        assert api.posts()[-1][3]["new_address"].endswith("1002호") and len(sess.receipts) == 1
        r1 = await ex.run("API_29", {"order_no": "100100001", "amount": 27900, "reason": "하자"})
        r2 = await ex.run("API_29", {"order_no": "100100001", "amount": 31900, "reason": "하자 전액"})
        assert r1["submitted"] and r2["duplicate"]
    run(go())


def test_F1_interleaved_tcs_keep_separate_sessions():
    async def go():
        api = FakeActionAPI()
        s = Settings(action_token="aitop100_t", db_path=":memory:")
        client = ActionClient(s.action_base_url, s.action_token, transport=api.transport())
        llm = ScriptedLLM(["A1", "B1", "A2"])
        agent = Agent(s, client, SessionStore(":memory:"), llm)
        await agent.handle("u", "- id: TC-A\n- 인입 계정: 회원 로그인 · 홍길동 · 010-****-2222\n주소 바꿔주세요")
        await agent.handle("u", "- id: TC-B\n판매자 정보 알려주세요")
        r = await agent.handle("u", "- id: TC-A\n100100001 이에요")
        ctx = llm.seen[-1][0]["content"]
        assert r.tc_id == "TC-A" and "인증됨 — 회원ID MB-1" in ctx
        hist = [m["content"] for m in llm.seen[-1][1:-1]]
        assert any("주소 바꿔주세요" in h for h in hist) and not any("판매자" in h for h in hist)
        # TC ID 없는 후속 메시지는 마지막 TC(TC-A)로 이어진다
        llm.script = ["A3"]
        r2 = await agent.handle("u", "경기 성남시 분당구 정자동 1 101동 1001호")
        assert r2.tc_id == "TC-A"
    run(go())
