"""LLM 도구 정의 + 실행기(권한·정책 가드, 캐시, 접수 중복 방지).

LLM은 40개 업무 API 전부에 접근할 수 있다(API-35는 escalate 도구로 감쌌다). reset 은 노출하지 않는다.
가드는 '고객에게 무엇을 보여 줄지'와 '어떤 접수를 허용할지'를 코드로 강제한다.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from typing import Any

from . import policy
from .action_client import ActionClient, ApiResult
from .api_registry import BUSINESS_OPERATIONS, BY_TOOL_NAME, OPERATIONS, Operation, RequestValidationError, receipt_id
from .config import Settings
from .parser import digits, phone_matches
from .session import Session, SessionStore

log = logging.getLogger("gyodong.tools")

LANES = ("LANE1_BOT", "LANE2_HANDOFF", "LANE3_CLAIM")
TARGETS = ("SECURITY", "SAFETY_LEGAL", "LOGISTICS", "SUPPLY", "OPS")
PRIORITIES = ("위기", "긴급", "일반")
CARD_WORDS = ("CARD", "카드")
DISCRETION = policy.BOT_DISCRETION_LIMIT

# 접수 API별 '대상' 식별자(같은 대상 재접수 = 덮어쓰기 위험)
POST_TARGET_PARAM = {
    "API-22": "order_no", "API-23": "order_no", "API-24": "order_no", "API-25": "order_no", "API-26": "order_no",
    "API-27": "order_no", "API-38": "order_no", "API-28": "shipment_id", "API-37": "shipment_id",
    "API-31": "approval_no", "API-32": "approval_no", "API-33": "member_id", "API-34": "member_id",
    "API-39": "sku", "API-40": "subscription_id",
}

HELPER_TOOLS: list[dict] = [
    {"name": "escalate", "description": "에스컬레이션 접수(API-35 POST /api/escalations). LANE2는 target 필수. 반환: 접수번호와 회신 기한.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "lane": {"type": "string", "enum": list(LANES)},
         "target": {"type": "string", "enum": list(TARGETS) + ["NONE"], "description": "LANE2 이관 대상. LANE3면 NONE 가능"},
         "priority": {"type": "string", "enum": list(PRIORITIES)},
         "reason": {"type": "string", "description": "조회로 확인한 사실(주문·결제·행사 기록 유무, 결제 여부)과 요청 요약. 개인정보 최소화"}},
         "required": ["lane", "target", "priority", "reason"]}},
    {"name": "policy_defect_deadline", "description": "하자 접수 기한 판정(신고 시점 기준 구판3일/개정7일, 역일).",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "received_date": {"type": "string", "description": "수령일 YYYY-MM-DD(배송 delivered_at)"},
         "report_date": {"type": "string", "description": "신고(접수)일 YYYY-MM-DD"}}, "required": ["received_date", "report_date"]}},
    {"name": "policy_subscription_cutoff", "description": "정기배송 컷오프(결제일 3영업일 전 24:00)와 요청 반영 회차 판정.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "payment_date": {"type": "string"}, "request_datetime": {"type": "string", "description": "요청 시각 YYYY-MM-DDTHH:MM"}},
         "required": ["payment_date", "request_datetime"]}},
    {"name": "policy_business_deadline", "description": "N영업일 기한(접수일 불산입, N일차 24:00). 이관 회신 기한 등.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "start_date": {"type": "string"}, "n_business_days": {"type": "integer"}}, "required": ["start_date", "n_business_days"]}},
    {"name": "policy_price_drop", "description": "구매 후 가격 인하 차액 보상 판정(주문 시점으로 구판/개정판 선택, 최소 보상쿠폰 산출).",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "order_date": {"type": "string"}, "paid_unit_amount": {"type": "integer", "description": "해당 SKU 1개 실결제액"},
         "new_normal_price": {"type": ["integer", "null"]}, "drop_date": {"type": ["string", "null"]},
         "normal_price_drop_confirmed": {"type": ["boolean", "null"], "description": "정상가 인하가 기록으로 확인됐으면 true, 한정 프로모션가뿐이면 false, 확인 불가면 null"},
         "limited_promo_only": {"type": ["boolean", "null"]}, "already_compensated": {"type": "boolean"}},
         "required": ["order_date", "paid_unit_amount"]}},
    {"name": "policy_weight_check", "description": "중량 판정(이상표기=절대하한, 정량표기 ±5%, 수산물 표기 대비 8%).",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "listed_weight": {"type": "string", "description": "예: '8kg 이상', '1kg'"}, "measured_kg": {"type": "number"},
         "seafood": {"type": "boolean"}, "shipped_kg": {"type": ["number", "null"]}, "paid_amount": {"type": ["integer", "null"]}},
         "required": ["listed_weight", "measured_kg"]}},
    {"name": "policy_promo_validity", "description": "프로모션 유효기간 판정(결제 완료 시각 기준, valid_until 당일 24:00까지).",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "valid_from": {"type": "string"}, "valid_until": {"type": ["string", "null"]}, "paid_at": {"type": "string"}},
         "required": ["valid_from", "paid_at"]}},
    {"name": "calendar_info", "description": "2037년 날짜의 영업일·출고일·공휴일 여부와 다음 출고일.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {"date": {"type": "string"}}, "required": ["date"]}},
    {"name": "compare_order_address", "description": "고객이 제시한 주소가 본인 주문의 배송지와 일치하는지 대조(저장 주소를 읽어 주지 않는다).",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "order_no": {"type": "string"}, "address_claimed": {"type": "string"}}, "required": ["order_no", "address_claimed"]}},
    {"name": "set_test_case_id", "description": "고객/평가 메시지에 적힌 TC ID를 이 상담의 Action API 헤더 값으로 설정(메시지에 실제로 있는 값만).",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {"tc_id": {"type": "string"}}, "required": ["tc_id"]}},
    {"name": "register_inbound_account", "description": "상담 첫머리에 채널이 표시한 인입 계정(명의·연락처·회원ID)을 시스템과 대조해 인증 회원을 확정. 고객이 본문에서 말한 이름·번호에는 쓰지 않는다.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "name": {"type": ["string", "null"]}, "phone": {"type": ["string", "null"]}, "member_id": {"type": ["string", "null"]}}}},
]


def _api_tool_spec(op: Operation) -> dict:
    props: dict[str, Any] = {}
    required: list[str] = []
    for p in op.path_params:
        props[p] = {"type": "string", "description": "경로 파라미터"}
        required.append(p)
    if op.query_param:
        props[op.query_param] = {"type": "string", "description": "검색 파라미터(정확히 일치)"}
        required.append(op.query_param)
    if op.body_schema and op.method == "POST":
        for k, v in (op.body_schema.get("properties") or {}).items():
            props[k] = {kk: vv for kk, vv in v.items() if kk in ("type", "enum", "description", "items")}
        required += [r for r in op.body_schema.get("required", []) if r not in required]
    kind = "접수(POST — 정책 확인 후에만)" if op.method == "POST" else "조회(GET)"
    desc = f"[{op.op_id}] {op.summary} — {op.method} {op.path}{'?' + op.query_param + '=' if op.query_param else ''} · {kind}"
    if op.description:
        desc += f" · {op.description}"
    return {"type": "function", "function": {"name": op.tool_name, "description": desc, "parameters": {
        "type": "object", "additionalProperties": False, "properties": props, "required": required}}}


def tool_specs() -> list[dict]:
    specs = [_api_tool_spec(op) for op in BUSINESS_OPERATIONS.values() if op.op_id != "API-35"]
    specs += [{"type": "function", "function": h} for h in HELPER_TOOLS]
    return specs


def _coerce(op: Operation, k: str, v: Any) -> Any:
    """qwen3_coder XML 인자 등에서 들어온 값 타입을 원문 스키마에 맞춘다(문자열↔정수)."""
    if k in op.path_params or k == op.query_param:
        return str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
    t = ((op.body_schema or {}).get("properties") or {}).get(k, {}).get("type")
    if t == "integer" and isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip().replace(",", "")):
        return int(v.strip().replace(",", ""))
    if t == "string" and isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    if t == "array" and isinstance(v, str):
        return [v]
    return v


def _split_args(op: Operation, args: dict) -> tuple[dict, dict | None]:
    params, body = {}, {}
    args = {k: _coerce(op, k, v) for k, v in (args or {}).items()}
    for k, v in args.items():
        if k in op.path_params or k == op.query_param:
            params[k] = v
        else:
            body[k] = v
    if op.method == "GET":
        return params, (body or None)
    return params, body


def _strip_none(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _strip_none(v) for k, v in o.items() if v not in (None, [], "")}
    if isinstance(o, list):
        return [_strip_none(x) for x in o]
    return o


def _escalation_lane_value(lane: str, target: str | None) -> str:
    fmt = os.environ.get("ESCALATION_LANE_FORMAT", "{lane}")
    return fmt.format(lane=lane, target=(target or "")).rstrip(":")


class ToolExecutor:
    def __init__(self, settings: Settings, client: ActionClient, store: SessionStore, session: Session):
        self.s = settings
        self.client = client
        self.store = store
        self.sess = session
        self.trace: list[dict] = []
        self.current_text = ""

    # ------------------------------------------------------------------ 공통 호출
    @property
    def tc_id(self) -> str:
        return self.sess.tc_id or self.s.default_tc_id

    async def _raw(self, op_id: str, params: dict | None = None, body: dict | None = None,
                   use_cache: bool = True) -> ApiResult:
        op = OPERATIONS[op_id]
        ck = op_id + "|" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
        if op.method == "GET" and use_cache and ck in self.sess.cache:
            c = self.sess.cache[ck]
            return ApiResult(op_id, c["status"], c.get("data"), c.get("code"), c.get("message"), attempts=0)
        if not self.tc_id:
            return ApiResult(op_id, 400, error_code="NO_TC_ID", error_message="대화에서 TC ID를 받지 못해 호출하지 않음", attempts=0)
        if self.sess.api_calls >= self.s.per_tc_call_cap:
            return ApiResult(op_id, 429, error_code="TC_CAP", error_message="이 상담의 호출 상한 도달", attempts=0)
        try:
            res = await self.client.call(op_id, self.tc_id, params, body)
        except RequestValidationError as e:
            return ApiResult(op_id, 400, error_code="CLIENT_VALIDATION", error_message=str(e), attempts=0)
        self.sess.api_calls += max(1, res.attempts)
        self.store.incr("api_calls_total", max(1, res.attempts))
        self.trace.append({"op": op_id, "params": params, "status": res.status})
        if op.method == "GET" and res.status in (200, 404):
            self.sess.cache[ck] = {"status": res.status, "data": res.data}
        return res

    async def _order(self, order_no: str) -> dict | None:
        if order_no in self.sess.orders:
            return self.sess.orders[order_no]
        r = await self._raw("API-07", {"order_no": order_no})
        if r.ok and isinstance(r.data, dict):
            self.sess.orders[order_no] = r.data
            self.sess.owned_orders[order_no] = self._is_owner(r.data.get("member_id"))
            return r.data
        return None

    def _is_owner(self, member_id: str | None) -> bool:
        if self.sess.verified_member_id:
            return member_id == self.sess.verified_member_id
        # lenient 모드: 인입 계정 표시가 아예 없는 대화에서만 귀속 확인을 생략
        return self.s.auth_mode == "lenient" and not self.sess.inbound

    def _deny(self, what: str, exists: bool | None = None) -> dict:
        if not self.sess.verified_member_id:
            d = {"access": "UNVERIFIED", "message": f"{what}: 인입 계정 인증이 없어 안내·처리 불가. 로그인한 상담 채널 계정(본인 명의)으로 문의 안내. 이름·전화·주문번호를 아는 것은 인증이 아님"}
        else:
            d = {"access": "DENIED", "message": f"{what}: 요청자 계정에 귀속되지 않음. 상태·주소·수령인 등 상세를 말하지 말고 본인 주문을 다시 확인해 달라고 안내"}
        if exists is not None:
            d["record_exists"] = exists
        return d

    # ------------------------------------------------------------------ 데이터 정리(고객에게 읽어 주면 안 되는 값 제거)
    def _clean_member(self, m: dict) -> dict:
        return {k: m.get(k) for k in ("member_id", "name", "member_type", "grade", "status", "joined_at",
                                      "referred_by_member_id")}

    def _clean_order(self, o: dict) -> dict:
        d = {k: v for k, v in o.items() if k not in ("shipping_address", "recipient_name")}
        mem_name = (self.sess.verified_member or {}).get("name")
        d["recipient"] = ("주문자 본인" if mem_name and o.get("recipient_name") == mem_name
                          else "제3자(선물 등) — 수령인 이름·주소·연락처 비공개")
        d["shipping_address"] = "(비공개 — compare_order_address 로 고객 제시 주소와 대조만 가능)"
        return d

    def _clean_payment(self, p: dict) -> dict:
        d = dict(p)
        mem_name = (self.sess.verified_member or {}).get("name")
        d["payer_is_member"] = bool(mem_name) and p.get("payer_name") == mem_name
        d.pop("payer_name", None)
        return d

    # ------------------------------------------------------------------ 인입 계정 확인
    async def identify(self, name: str | None, phone: str | None, member_id: str | None) -> dict:
        self.sess.identify_attempted = True
        if member_id:
            r = await self._raw("API-12", {"member_id": member_id})
            if r.ok and isinstance(r.data, dict):
                m = r.data
                if (not name or m.get("name") == name) and (not phone or phone_matches(phone, m.get("phone"))):
                    return self._set_verified(m)
            return {"verified": False, "message": "인입 계정 정보와 일치하는 회원을 확인하지 못함"}
        if name:
            r = await self._raw("API-13", {"name": name})
            if r.ok and isinstance(r.data, list):
                cands = [m for m in r.data if not phone or phone_matches(phone, m.get("phone"))]
                if len(cands) == 1 and phone:
                    return self._set_verified(cands[0])
                if len(cands) > 1 or (len(cands) == 1 and not phone):
                    return {"verified": False, "message": "동명이인 등으로 계정 특정 불가 — 연락처 뒷자리·주문번호 등 추가 식별정보를 고객이 제시하도록 요청"}
            return {"verified": False, "message": "인입 계정과 일치하는 회원을 확인하지 못함(비회원일 수 있음)"}
        return {"verified": False, "message": "인입 계정 정보 없음"}

    def _set_verified(self, m: dict) -> dict:
        self.sess.verified_member_id = m.get("member_id")
        self.sess.verified_member = m
        return {"verified": True, "member": self._clean_member(m)}

    # ------------------------------------------------------------------ 디스패치
    async def run(self, name: str, args: dict) -> dict:
        try:
            if name in BY_TOOL_NAME:
                op = BY_TOOL_NAME[name]
                if op.op_id == "API-35":
                    return {"blocked": True, "message": "escalate 도구를 사용"}
                params, body = _split_args(op, args)
                if op.method == "GET":
                    return await self._get(op, params)
                return await self._post(op, params, body or {})
            return await self._helper(name, args or {})
        except RequestValidationError as e:
            return {"error": "요청 형식 오류(호출하지 않음)", "detail": str(e)}
        except Exception as e:  # 도구 하나의 실패가 상담 전체를 멈추지 않게
            log.exception("tool error %s", name)
            return {"error": f"{type(e).__name__}", "detail": str(e)[:200]}

    # ------------------------------------------------------------------ GET 가드
    async def _get(self, op: Operation, params: dict) -> dict:
        oid = op.op_id
        vm = self.sess.verified_member_id
        if oid in ("API-07", "API-11", "API-18", "API-30"):
            order_no = str(params.get("order_no", "")).strip()
            order = await self._order(order_no)
            if order is None:
                r = await self._raw("API-07", {"order_no": order_no})
                return r.summary_for_llm() if not r.ok else {"error": "주문 조회 실패"}
            if not self._is_owner(order.get("member_id")):
                return self._deny(f"주문 {order_no}", exists=True)
            if oid == "API-07":
                return {"status": 200, "data": _strip_none(self._clean_order(order))}
            r = await self._raw(oid, params)
            if r.ok and oid == "API-11" and isinstance(r.data, list):
                for sh in r.data:
                    self.sess.shipments[sh.get("shipment_id")] = sh
            if r.ok and oid == "API-18" and isinstance(r.data, list):
                for p in r.data:
                    self.sess.payments[p.get("approval_no")] = p
                return {"status": 200, "data": [_strip_none(self._clean_payment(p)) for p in r.data]}
            return r.summary_for_llm()
        if oid == "API-10":
            r = await self._raw(oid, params)
            if not r.ok:
                return r.summary_for_llm()
            sh = r.data or {}
            order = await self._order(str(sh.get("order_no")))
            if not order or not self._is_owner(order.get("member_id")):
                return self._deny(f"배송 {params.get('shipment_id')}", exists=True)
            self.sess.shipments[sh.get("shipment_id")] = sh
            return {"status": 200, "data": _strip_none(sh)}
        if oid == "API-17":
            r = await self._raw(oid, params)
            if not r.ok:
                return r.summary_for_llm()
            p = r.data or {}
            self.sess.payments[p.get("approval_no")] = p
            allowed = False
            if p.get("order_no"):
                order = await self._order(str(p["order_no"]))
                allowed = bool(order) and self._is_owner(order.get("member_id"))
            elif vm:
                allowed = p.get("payer_name") == (self.sess.verified_member or {}).get("name")
            if not allowed:
                return self._deny(f"결제 {params.get('approval_no')}", exists=True)
            return {"status": 200, "data": _strip_none(self._clean_payment(p))}
        if oid in ("API-05", "API-15", "API-16"):
            if not vm or params.get("member_id") != vm:
                return self._deny("다른 회원의 상담·적립금·쿠폰 정보")
            r = await self._raw(oid, params)
            return r.summary_for_llm()
        if oid == "API-08":
            mid = params.get("member_id")
            if vm and mid == vm:
                r = await self._raw(oid, params)
                if r.ok and isinstance(r.data, list):
                    for o in r.data:
                        self.sess.orders[o["order_no"]] = o
                        self.sess.owned_orders[o["order_no"]] = True
                    return {"status": 200, "data": [_strip_none(self._clean_order(o)) for o in r.data[:30]]}
                return r.summary_for_llm()
            if mid in self.sess.referred_ids:
                r = await self._raw(oid, params)
                if r.ok and isinstance(r.data, list):
                    return {"status": 200, "note": "피추천인 첫 구매 확인용 최소 정보",
                            "data": [{"order_no": o.get("order_no"), "status": o.get("status"),
                                      "ordered_at": o.get("ordered_at"), "status_changed_at": o.get("status_changed_at")}
                                     for o in r.data]}
                return r.summary_for_llm()
            return self._deny("다른 회원의 주문 내역")
        if oid == "API-12":
            mid = params.get("member_id")
            if vm and mid == vm:
                r = await self._raw(oid, params)
                return {"status": r.status, "data": self._clean_member(r.data)} if r.ok else r.summary_for_llm()
            if mid in self.sess.referred_ids:
                r = await self._raw(oid, params)
                if r.ok:
                    return {"status": 200, "data": {k: r.data.get(k) for k in ("member_id", "status", "joined_at", "referred_by_member_id")}}
                return r.summary_for_llm()
            return self._deny("다른 회원 정보")
        if oid == "API-13":
            name = params.get("name")
            inbound = self.sess.inbound or {}
            if name and name in (inbound.get("name"), (self.sess.verified_member or {}).get("name")):
                r = await self._raw(oid, params)
                if r.ok and isinstance(r.data, list):
                    return {"status": 200, "data": [{"member_id": m.get("member_id"),
                                                     "phone_matches_inbound": phone_matches(inbound.get("phone"), m.get("phone"))}
                                                    for m in r.data]}
                return r.summary_for_llm()
            return {"access": "DENIED", "message": "이름으로 다른 고객을 찾아 주지 않는다(개인정보)"}
        if oid == "API-14":
            if not vm or params.get("referred_by") != vm:
                return self._deny("다른 회원의 추천 내역")
            r = await self._raw(oid, params)
            if r.ok and isinstance(r.data, list):
                self.sess.referred_ids = [m.get("member_id") for m in r.data]
                return {"status": 200, "data": [{k: m.get(k) for k in ("member_id", "status", "joined_at")} for m in r.data]}
            return r.summary_for_llm()
        if oid == "API-19":
            r = await self._raw(oid, params)
            if not r.ok:
                return r.summary_for_llm()
            if not self._is_owner((r.data or {}).get("member_id")):
                return self._deny(f"구독 {params.get('subscription_id')}", exists=True)
            self.sess.subscriptions[r.data["subscription_id"]] = r.data
            return {"status": 200, "data": r.data}
        if oid == "API-06":
            r = await self._raw(oid, params)
            if r.ok and isinstance(r.data, list):
                return {"status": 200, "count": len(r.data), "data": [
                    {"ticket_id": t.get("ticket_id"), "created_at": t.get("created_at"),
                     "mine": t.get("member_id") == vm, "content": (t.get("content") or "")[:160]} for t in r.data[:25]]}
            return r.summary_for_llm()
        if oid == "API-20":
            r = await self._raw(oid, params)
            self.sess.known_promos[str(params.get("code", "")).upper()] = r.ok
            if r.status == 404:
                return {"status": 404, "message": "프로모션 원장에 해당 코드 단건이 없음(발행 기록 확인되지 않음)"}
            return r.summary_for_llm()
        # 상품·로트·조사·재고·에스컬레이션 조회: 공개 범위
        r = await self._raw(oid, params)
        return r.summary_for_llm()

    # ------------------------------------------------------------------ POST 가드
    async def _post(self, op: Operation, params: dict, body: dict) -> dict:
        oid = op.op_id
        # 1) 형식 검증(서버 400 방지) — 실패 시 호출 0회
        op.build(dict(params), dict(body))
        vm = self.sess.verified_member_id
        lenient = self.s.auth_mode == "lenient" and not self.sess.inbound
        if not vm and not lenient:
            return {"blocked": True, "reason": "인입 계정 인증 없음 — 주문·결제·회원 대상 접수 불가. 로그인한 상담 채널로 본인 확인 후 진행 안내(사칭·안전 사안은 escalate)"} \
                if oid != "API-39" else await self._submit(op, params, body, target=str(params.get("sku")))
        # 2) 대상 귀속 확인
        target = None
        if oid in ("API-22", "API-23", "API-24", "API-25", "API-26", "API-27", "API-38"):
            target = str(params["order_no"])
            order = await self._order(target)
            if not order:
                return {"blocked": True, "reason": f"주문 {target} 을 확인하지 못함"}
            if not self._is_owner(order.get("member_id")):
                return {"blocked": True, **self._deny(f"주문 {target}", exists=True)}
            if oid == "API-27" and int(body.get("qty", 0)) <= 0:
                return {"blocked": True, "reason": "qty 는 1 이상"}
            if oid == "API-38" and int(body.get("qty", 0)) <= 0:
                return {"blocked": True, "reason": "qty 는 1 이상"}
        elif oid in ("API-28", "API-37"):
            target = str(params["shipment_id"])
            sh = self.sess.shipments.get(target)
            if not sh:
                r = await self._raw("API-10", {"shipment_id": target})
                if not r.ok:
                    return {"blocked": True, "reason": f"배송 {target} 확인 실패({r.status})"}
                sh = r.data
                self.sess.shipments[target] = sh
            order = await self._order(str(sh.get("order_no")))
            if not order or not self._is_owner(order.get("member_id")):
                return {"blocked": True, **self._deny(f"배송 {target}", exists=True)}
            if oid == "API-37" and int(body.get("charge_amount", 0)) <= 0:
                return {"blocked": True, "reason": "청구액은 양수"}
        elif oid == "API-29":
            target = str(body.get("order_no"))
            order = await self._order(target)
            if not order:
                return {"blocked": True, "reason": f"주문 {target} 을 확인하지 못함"}
            if not self._is_owner(order.get("member_id")):
                return {"blocked": True, **self._deny(f"주문 {target}", exists=True)}
            amt = int(body.get("amount", 0))
            if amt <= 0:
                return {"blocked": True, "reason": "환불액은 양수"}
            if order.get("amount") is not None and amt > int(order["amount"]):
                return {"blocked": True, "reason": f"환불액 {amt}원이 주문 실결제액 {order['amount']}원을 초과"}
            if amt > DISCRETION and not self._is_full_or_item_amount(order, amt):
                return {"blocked": True, "reason": "5만원 초과 부분환불은 봇 재량 밖 — escalate(LANE2_HANDOFF, OPS)로 이관(분할 접수 금지)"}
        elif oid in ("API-31", "API-32"):
            target = str(params["approval_no"])
            p = self.sess.payments.get(target)
            if not p:
                r = await self._raw("API-17", {"approval_no": target})
                if not r.ok:
                    return {"blocked": True, "reason": f"결제 {target} 확인 실패({r.status})"}
                p = r.data
                self.sess.payments[target] = p
            owned = False
            if p.get("order_no"):
                order = await self._order(str(p["order_no"]))
                owned = bool(order) and self._is_owner(order.get("member_id"))
            else:
                owned = p.get("payer_name") == (self.sess.verified_member or {}).get("name")
            if not owned:
                return {"blocked": True, **self._deny(f"결제 {target}", exists=True)}
            if p.get("status") != "APPROVED":
                return {"blocked": True, "reason": f"결제 상태가 {p.get('status')} — 접수 불가"}
            is_card = any(w in str(p.get("pay_method", "")).upper() for w in CARD_WORDS)
            if oid == "API-31" and not is_card:
                return {"blocked": True, "reason": "카드 결제가 아니어서 카드 취소 대상 아님(원결제수단으로 환불 신청 검토)"}
            if oid == "API-32" and is_card:
                return {"blocked": True, "reason": "카드 결제는 카드 매출전표가 증빙 — 현금영수증 중복 발행 불가"}
        elif oid in ("API-33", "API-34"):
            target = str(params["member_id"])
            if target != vm and not lenient:
                return {"blocked": True, "reason": "인증 회원 본인 계정에만 접수 가능"}
            if oid == "API-33":
                code = str(body.get("promo_code", "")).strip().upper()
                body["promo_code"] = code
                if code not in self.sess.known_promos:
                    r = await self._raw("API-20", {"code": code})
                    self.sess.known_promos[code] = r.ok
                if not self.sess.known_promos.get(code):
                    return {"blocked": True, "reason": f"프로모션 원장에 없는 코드({code}) — 임의 코드 발급 불가"}
        elif oid == "API-40":
            target = str(params["subscription_id"])
            sub = self.sess.subscriptions.get(target)
            if not sub:
                r = await self._raw("API-19", {"subscription_id": target})
                if not r.ok:
                    return {"blocked": True, "reason": f"구독 {target} 확인 실패({r.status})"}
                sub = r.data
                self.sess.subscriptions[target] = sub
            if not self._is_owner(sub.get("member_id")):
                return {"blocked": True, **self._deny(f"구독 {target}", exists=True)}
            if sub.get("status") == "CANCELED":
                return {"blocked": True, "reason": "이미 해지된 구독"}
        elif oid == "API-39":
            target = str(params["sku"])
        return await self._submit(op, params, body, target)

    def _is_full_or_item_amount(self, order: dict, amt: int) -> bool:
        if amt == int(order.get("amount") or -1):
            return True
        items = order.get("items") or []
        totals = [int(i.get("unit_price", 0)) * int(i.get("qty", 0)) for i in items]
        units = [int(i.get("unit_price", 0)) for i in items]
        return amt in totals or amt in units or amt == sum(totals)

    async def _submit(self, op: Operation, params: dict, body: dict, target: str | None) -> dict:
        target = target or params.get(POST_TARGET_PARAM.get(op.op_id, ""), "")
        for rc in self.sess.receipts:
            if rc["op"] == op.op_id and rc["target"] == target:
                return {"duplicate": True, "receipt_id": rc["receipt_id"],
                        "message": "같은 대상에 이미 접수됨 — 재접수하지 않음(덮어쓰기 방지). 기존 접수번호로 안내"}
        r = await self._raw(op.op_id, params, body, use_cache=False)
        if not r.ok:
            out = r.summary_for_llm()
            out["submitted"] = False
            return out
        rid = receipt_id(op, r.data)
        self.sess.receipts.append({"op": op.op_id, "target": target, "body": body, "receipt_id": rid,
                                   "requested_at": (r.data or {}).get("requested_at")})
        # 접수 후 갱신되는 필드(orders.refund_ids 등) 캐시 무효화
        if op.op_id in ("API-29", "API-23") and target in self.sess.orders:
            self.sess.orders.pop(target, None)
            self.sess.cache = {k: v for k, v in self.sess.cache.items() if not k.startswith("API-07|")}
        return {"submitted": True, "receipt_id": rid, "request_status": (r.data or {}).get("request_status"),
                "requested_at": (r.data or {}).get("requested_at"),
                "note": "접수만 됨(처리 완료 아님). 고객에게는 '접수'와 이 접수번호만 안내"}

    # ------------------------------------------------------------------ 보조 도구
    async def _helper(self, name: str, a: dict) -> dict:
        if name == "escalate":
            lane = a.get("lane")
            target = a.get("target") if a.get("target") not in (None, "", "NONE") else None
            prio = a.get("priority") or "일반"
            if lane not in LANES:
                return {"blocked": True, "reason": f"lane 은 {LANES} 중 하나"}
            if lane == "LANE2_HANDOFF" and target not in TARGETS:
                return {"blocked": True, "reason": f"LANE2 이관 대상은 {TARGETS} 중 하나"}
            reason = str(a.get("reason", "")).strip()
            if not reason:
                return {"blocked": True, "reason": "사유 필요"}
            prefix = ""
            if self.s.escalation_target_in_reason:
                prefix = f"[{target or lane}][{prio}] "
            body = {"lane": _escalation_lane_value(lane, target), "reason": (prefix + reason)[:1000]}
            key = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
            for rc in self.sess.receipts:
                if rc["op"] == "API-35" and (rc["target"] == key or rc.get("lane_target") == f"{lane}/{target}"):
                    return {"duplicate": True, "receipt_id": rc["receipt_id"], "message": "같은 레인·대상으로 이미 이관됨"}
            r = await self._raw("API-35", None, body, use_cache=False)
            if not r.ok:
                out = r.summary_for_llm()
                out["submitted"] = False
                return out
            rid = receipt_id(OPERATIONS["API-35"], r.data)
            req_at = (r.data or {}).get("requested_at") or self.s.world_now
            self.sess.receipts.append({"op": "API-35", "target": key, "lane_target": f"{lane}/{target}",
                                       "body": body, "receipt_id": rid, "requested_at": req_at})
            dl = policy.business_deadline(str(req_at)[:10], 3)
            return {"submitted": True, "escalation_id": rid, "requested_at": req_at,
                    "reply_deadline": dl["deadline"], "note": "접수번호와 회신 기한을 안내. 결론 예측·승인 표현 금지"}
        if name == "policy_defect_deadline":
            return policy.defect_report_track(a["received_date"], a["report_date"])
        if name == "policy_subscription_cutoff":
            return policy.subscription_cutoff(a["payment_date"], a["request_datetime"])
        if name == "policy_business_deadline":
            return policy.business_deadline(a["start_date"], int(a.get("n_business_days", 3)))
        if name == "policy_price_drop":
            return policy.price_drop_compensation(
                a["order_date"], int(a["paid_unit_amount"]), a.get("new_normal_price"), a.get("drop_date"),
                a.get("normal_price_drop_confirmed"), a.get("limited_promo_only"), bool(a.get("already_compensated")))
        if name == "policy_weight_check":
            return policy.weight_check(a["listed_weight"], float(a["measured_kg"]), bool(a.get("seafood")),
                                       a.get("shipped_kg"), a.get("paid_amount"))
        if name == "policy_promo_validity":
            return policy.promo_validity(a["valid_from"], a.get("valid_until"), a["paid_at"])
        if name == "calendar_info":
            return policy.calendar_info(a["date"])
        if name == "compare_order_address":
            order = await self._order(str(a["order_no"]))
            if not order or not self._is_owner(order.get("member_id")):
                return self._deny(f"주문 {a['order_no']}")
            norm = lambda s: re.sub(r"[\s,.-]", "", s or "")
            return {"matches": norm(a["address_claimed"]) == norm(order.get("shipping_address")) or
                    (len(norm(a["address_claimed"])) >= 6 and norm(a["address_claimed"]) in norm(order.get("shipping_address")))}
        if name == "set_test_case_id":
            from .api_registry import TC_PATTERN
            v = str(a.get("tc_id", "")).strip()
            seen = " ".join(m.get("content") or "" for m in self.sess.history if m.get("role") == "user") + " " + self.current_text
            if not TC_PATTERN.match(v) or v not in seen:
                return {"ok": False, "message": "메시지에 없는 값이거나 형식 오류"}
            if self.sess.tc_id and self.sess.tc_id != v and self.sess.api_calls:
                return {"ok": False, "message": f"이미 TC {self.sess.tc_id} 로 진행 중 — 한 TC 동안 ID를 바꾸지 않는다"}
            self.sess.tc_id = v
            return {"ok": True, "tc_id": v}
        if name == "register_inbound_account":
            first = self.sess.first_message or ""
            vals = [v for v in (a.get("name"), a.get("phone"), a.get("member_id")) if v]
            if not vals or not all((v in first) or (digits(v) and digits(v) in digits(first)) for v in vals):
                return {"verified": False, "message": "상담 첫머리 인입 계정 표시에서 확인되지 않는 값 — 고객 본문 주장은 인증이 아님"}
            if self.sess.verified_member_id:
                return {"verified": True, "member": self._clean_member(self.sess.verified_member)}
            return await self.identify(a.get("name"), a.get("phone"), a.get("member_id"))
        return {"error": f"알 수 없는 도구 {name}"}
