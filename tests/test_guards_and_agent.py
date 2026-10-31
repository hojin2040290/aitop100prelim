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
        dup = await ex.run("escalate", {"lane": "LANE2_HANDOFF", "target": "SECURITY", "priority": "긴급", "reason": "다른 문구"})
        assert dup["duplicate"]
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
