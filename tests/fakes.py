"""테스트 더블: 가짜 Action API(httpx.MockTransport)와 순서대로 답하는 가짜 LLM."""
from __future__ import annotations

import json
import re
from collections import Counter

import httpx

from gyodong_agent.llm import LLMReply, ToolCall

MEMBERS = {
    "MB-1": {"member_id": "MB-1", "name": "홍길동", "phone": "010-1111-2222", "birth_year": 1980, "member_type": "INDIVIDUAL",
             "grade": "MEMBER", "status": "ACTIVE", "address": "제주 어딘가 1", "joined_at": "2037-03-10", "referred_by_member_id": None},
    "MB-2": {"member_id": "MB-2", "name": "김타인", "phone": "010-3333-4444", "birth_year": 1990, "member_type": "INDIVIDUAL",
             "grade": "REGULAR", "status": "ACTIVE", "address": "서울 어딘가 2", "joined_at": "2037-03-11", "referred_by_member_id": "MB-1"},
}


def _order(no, member, amount, items, status="CONFIRMED"):
    return {"order_no": no, "member_id": member, "status": status, "status_changed_at": None,
            "ordered_at": "2037-06-20T10:00:00+09:00", "amount": amount, "recipient_name": MEMBERS[member]["name"],
            "shipping_address": MEMBERS[member]["address"], "inflow_tag": None, "ship_scheduled_at": "2037-06-22",
            "failure_code": None, "payment_refs": [f"PAY-{no}"], "refund_ids": [], "change_request_ids": [], "items": items}


ORDERS = {
    "100100001": _order("100100001", "MB-1", 31900, [{"sku": "WTM-SEL-8", "name": "당도선별 수박", "qty": 1, "unit_price": 27900}]),
    "100100002": _order("100100002", "MB-2", 28000, [{"sku": "HGL-STD-5", "name": "하우스 감귤 5kg", "qty": 1, "unit_price": 24000}]),
    "100100003": _order("100100003", "MB-1", 124000, [{"sku": "HGL-STD-10", "name": "하우스 감귤 10kg", "qty": 2, "unit_price": 45000},
                                                     {"sku": "HGL-SEL-5", "name": "선별 감귤", "qty": 1, "unit_price": 30000}]),
}
SHIPMENTS = {
    "SHP-100100001-01": {"shipment_id": "SHP-100100001-01", "order_no": "100100001", "status": "DELIVERED", "carrier": "시원배송",
                         "invoice_no": "1", "picked_up_at": "2037-06-22T15:00:00", "delivered_at": "2037-06-24T11:00:00",
                         "delivered_location": "문앞", "return_reason": None, "item_condition": None, "ship_notice_sent_at": None,
                         "items": [{"sku": "WTM-SEL-8", "qty": 1, "lot_id": "KD-WTM-370624-02"}]},
}
PAYMENTS = {
    "PAY-100100001": {"approval_no": "PAY-100100001", "order_no": "100100001", "pay_method": "CARD", "amount": 31900,
                      "paid_at": "2037-06-20T10:00:00", "status": "APPROVED", "payer_name": "홍길동",
                      "cancellation_request_ids": [], "card_last4": "1234"},
    "PAY-100100003": {"approval_no": "PAY-100100003", "order_no": "100100003", "pay_method": "BANK_TRANSFER", "amount": 124000,
                      "paid_at": "2037-06-20T10:00:00", "status": "APPROVED", "payer_name": "홍길동",
                      "cancellation_request_ids": [], "card_last4": None},
}
PROMOS = {"CARE5000": {"code": "CARE5000", "name": "보상 5천", "benefit_type": "AMOUNT", "benefit_value": 5000,
                       "valid_from": "2037-03-02", "valid_until": None, "target_skus": None, "stackable_with": ["DISCOUNT_CODE"]}}
SUBS = {"SUB-1": {"subscription_id": "SUB-1", "member_id": "MB-1", "sku": "VEG-STD-5", "status": "ACTIVE", "interval": "WEEKLY",
                  "started_at": "2037-04-01"}}

RECEIPT_KEY = {"orders": "request_id", "shipments": "request_id", "payments": "request_id", "members": "request_id",
               "products": "request_id", "subscriptions": "request_id"}


class FakeActionAPI:
    def __init__(self):
        self.calls: list[tuple[str, str, dict, dict | None, dict]] = []
        self.receipts: dict[tuple, str] = {}
        self.counter = Counter()
        self.fail_next: list[int] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _receipt(self, kind: str, target: str, field: str, body: dict):
        key = (kind, target)
        if key not in self.receipts:
            self.counter[kind] += 1
            self.receipts[key] = f"{kind.upper()}-{self.counter[kind]:03d}"
        return {field: self.receipts[key], "request_status": "SUBMITTED", "requested_at": "2037-06-30T10:00:00+09:00"}

    def handle(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        self.calls.append((req.method, req.url.path, dict(req.url.params), body, dict(req.headers)))
        if "x-aitop100-test-case-id" not in req.headers and not req.url.path.endswith("/reset"):
            return httpx.Response(400, json={"code": "MISSING_TEST_CASE_ID", "message": "x"})
        if self.fail_next:
            return httpx.Response(self.fail_next.pop(0))
        p, q = req.url.path, dict(req.url.params)
        if req.method == "GET":
            m = re.fullmatch(r"/api/orders/(\w+)", p)
            if m:
                o = ORDERS.get(m.group(1))
                return httpx.Response(200, json=o) if o else httpx.Response(404)
            if p == "/api/orders":
                return httpx.Response(200, json=[o for o in ORDERS.values() if o["member_id"] == q.get("member_id")])
            m = re.fullmatch(r"/api/members/([\w-]+)", p)
            if m:
                mm = MEMBERS.get(m.group(1))
                return httpx.Response(200, json=mm) if mm else httpx.Response(404)
            if p == "/api/members":
                if "name" in q:
                    return httpx.Response(200, json=[m for m in MEMBERS.values() if m["name"] == q["name"]])
                return httpx.Response(200, json=[m for m in MEMBERS.values() if m["referred_by_member_id"] == q.get("referred_by")])
            m = re.fullmatch(r"/api/shipments/([\w-]+)", p)
            if m:
                s = SHIPMENTS.get(m.group(1))
                return httpx.Response(200, json=s) if s else httpx.Response(404)
            if p == "/api/shipments":
                return httpx.Response(200, json=[s for s in SHIPMENTS.values() if s["order_no"] == q.get("order_no")])
            m = re.fullmatch(r"/api/payments/([\w-]+)", p)
            if m:
                pp = PAYMENTS.get(m.group(1))
                return httpx.Response(200, json=pp) if pp else httpx.Response(404)
            if p == "/api/payments":
                return httpx.Response(200, json=[x for x in PAYMENTS.values() if x["order_no"] == q.get("order_no")])
            m = re.fullmatch(r"/api/promos/([\w-]+)", p)
            if m:
                pr = PROMOS.get(m.group(1))
                return httpx.Response(200, json=pr) if pr else httpx.Response(404)
            m = re.fullmatch(r"/api/subscriptions/([\w-]+)", p)
            if m:
                s = SUBS.get(m.group(1))
                return httpx.Response(200, json=s) if s else httpx.Response(404)
            m = re.fullmatch(r"/api/escalations/([\w-]+)", p)
            if m:
                return httpx.Response(200, json={"escalation_id": m.group(1), "request_status": "SUBMITTED",
                                                 "requested_at": "2037-06-30T10:00:00", "lane": "LANE2_HANDOFF",
                                                 "reason": "x", "status": "PENDING"})
            if p in ("/api/tickets", "/api/point-entries", "/api/coupons", "/api/refunds", "/api/inventory", "/api/products"):
                return httpx.Response(200, json=[])
            if re.fullmatch(r"/api/(products|lots)/[\w.-]+(/investigation)?", p):
                return httpx.Response(404)
            return httpx.Response(404)
        # POST
        if p == "/api/refunds":
            return httpx.Response(200, json={**self._receipt("refund", body["order_no"], "refund_id", body), "order_no": body["order_no"]})
        if p == "/api/escalations":
            key = json.dumps(body, sort_keys=True, ensure_ascii=False)
            return httpx.Response(200, json=self._receipt("esc", key, "escalation_id", body))
        if p == "/api/action-data/reset":
            return httpx.Response(204)
        m = re.fullmatch(r"/api/(\w+(?:-\w+)?)/([\w.-]+)/([\w-]+)", p)
        if m:
            kind, target, action = m.groups()
            field = "memo_id" if action == "memos" else "request_id"
            return httpx.Response(200, json=self._receipt(f"{kind}-{action}", target, field, body))
        return httpx.Response(404)

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


class ScriptedLLM:
    """미리 정한 응답을 순서대로 돌려준다. 각 항목은 str(최종 답변) 또는 [(tool, args), ...]."""

    def __init__(self, script):
        self.script = list(script)
        self.seen: list[list[dict]] = []

    async def chat(self, messages, tools=None, tool_choice="auto", max_tokens=None):
        self.seen.append(list(messages))
        item = self.script.pop(0) if self.script else "확인했습니다."
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str) or tools is None:
            text = item if isinstance(item, str) else "최종 답변입니다."
            return LLMReply(content=text, tool_calls=[], raw_message={"role": "assistant", "content": text})
        calls = [ToolCall(f"c{i}", n, a) for i, (n, a) in enumerate(item)]
        raw = {"role": "assistant", "content": None, "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}} for c in calls]}
        return LLMReply(content="", tool_calls=calls, raw_message=raw)
