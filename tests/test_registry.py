import pytest

from gyodong_agent.api_registry import (ACTIONS_SHA256, BUSINESS_OPERATIONS, OPERATIONS, RESET_OP_ID,
                                        RequestValidationError, file_sha256, load_operations)
from gyodong_agent.tools import tool_specs

# 40개 업무 API 각각의 최소 유효 입력(경로/쿼리 + 본문)
SAMPLE_ARGS = {
    "API-01": ({"sku": "WTM-SEL-8"}, None), "API-02": ({"item": "WTM"}, None), "API-03": ({"lot_id": "KD-WTM-370624-02"}, None),
    "API-04": ({"lot_id": "KD-PTT-370622-01"}, None), "API-05": ({"member_id": "MB-1"}, None), "API-06": ({"lot_id": "L"}, None),
    "API-07": ({"order_no": "100100003"}, None), "API-08": ({"member_id": "MB-1"}, None), "API-09": ({"inflow_tag": "LIVE"}, None),
    "API-10": ({"shipment_id": "SHP-1"}, None), "API-11": ({"order_no": "1"}, None), "API-12": ({"member_id": "MB-1"}, None),
    "API-13": ({"name": "홍길동"}, None), "API-14": ({"referred_by": "MB-1"}, None), "API-15": ({"member_id": "MB-1"}, None),
    "API-16": ({"member_id": "MB-1"}, None), "API-17": ({"approval_no": "PAY-1"}, None), "API-18": ({"order_no": "1"}, None),
    "API-19": ({"subscription_id": "SUB-1"}, None), "API-20": ({"code": "SUBAK15"}, None), "API-21": ({"sku": "GAL-STD-1"}, None),
    "API-22": ({"order_no": "1"}, {}), "API-23": ({"order_no": "1"}, {"requested_items": ["HGL-STD-5 x1"]}),
    "API-24": ({"order_no": "1"}, {"new_address": "제주"}), "API-25": ({"order_no": "1"}, {"requested_date": "2037-07-03"}),
    "API-26": ({"order_no": "1"}, {"memo": "가격표 제거"}), "API-27": ({"order_no": "1"}, {"qty": 1, "reason": "지연"}),
    "API-28": ({"shipment_id": "S"}, {}), "API-29": ({}, {"order_no": "1", "amount": 1000, "reason": "하자"}),
    "API-30": ({"order_no": "1"}, None), "API-31": ({"approval_no": "P"}, {}), "API-32": ({"approval_no": "P"}, {"receipt_number": "01011112222"}),
    "API-33": ({"member_id": "MB-1"}, {"promo_code": "CARE5000"}), "API-34": ({"member_id": "MB-1"}, {}),
    "API-35": ({}, {"lane": "LANE2_HANDOFF", "reason": "x"}), "API-36": ({"escalation_id": "ESC-1"}, None),
    "API-37": ({"shipment_id": "S"}, {"charge_amount": 4000}),
    "API-38": ({"order_no": "1"}, {"qty": 1, "trigger": "CUSTOMER_REQUEST", "cost_bearer": "CUSTOMER"}),
    "API-39": ({"sku": "GAL-STD-1"}, {}), "API-40": ({"subscription_id": "SUB-1"}, {"kind": "SKIP"}),
}


def test_counts_41_and_checksum():
    ops = load_operations()
    assert len(ops) == 41
    assert sum(o.method == "GET" for o in ops.values()) == 23
    assert sum(o.method == "POST" and not o.is_reset for o in ops.values()) == 17
    assert RESET_OP_ID in ops and len(BUSINESS_OPERATIONS) == 40
    assert file_sha256() == ACTIONS_SHA256


@pytest.mark.parametrize("op_id", sorted(SAMPLE_ARGS))
def test_every_business_operation_builds(op_id):
    op = OPERATIONS[op_id]
    params, body = SAMPLE_ARGS[op_id]
    path, query, b = op.build(dict(params), body)
    assert "?" not in path and "{" not in path
    if op.query_param:
        assert query == {op.query_param: params[op.query_param]}
    if op.method == "POST":
        assert isinstance(b, dict)


def test_query_path_split():
    op = OPERATIONS["API-02"]
    assert op.raw_path == "/api/products?item=" and op.path == "/api/products" and op.query_param == "item"


def test_additional_properties_and_enum_rejected():
    with pytest.raises(RequestValidationError):
        OPERATIONS["API-29"].build({}, {"order_no": "1", "amount": 1, "reason": "x", "account": "1234"})
    with pytest.raises(RequestValidationError):
        OPERATIONS["API-40"].build({"subscription_id": "S"}, {"kind": "PAUSE"})
    with pytest.raises(RequestValidationError):
        OPERATIONS["API-38"].build({"order_no": "1"}, {"qty": 1, "trigger": "x", "cost_bearer": "BOTH"})
    with pytest.raises(RequestValidationError):
        OPERATIONS["API-28"].build({"shipment_id": "S"}, {"reason": "x"})
    with pytest.raises(RequestValidationError):
        OPERATIONS["API-07"].build({"order_no": "1", "member_id": "x"}, None)
    with pytest.raises(RequestValidationError):
        OPERATIONS["API-07"].build({}, None)


def test_reset_not_exposed_to_llm():
    names = {t["function"]["name"] for t in tool_specs()}
    assert "resetMyActionData" not in names and not any("reset" in n.lower() for n in names)
    # 업무 API 39개 직접 + API-35는 escalate 도구로 노출 → 40개 모두 접근 가능
    api_tools = {n for n in names if n.startswith("API_")}
    assert len(api_tools) == 39 and "API_35" not in api_tools and "escalate" in names
