from gyodong_agent.config import Settings
from gyodong_agent.parser import extract_inbound, extract_tc_id, phone_matches, strip_tc_marker

MARK = Settings().inbound_marker_regex


def test_tc_id_variants():
    assert extract_tc_id("TC ID: PUB-TC-007\n주문 취소하고 싶어요") == "PUB-TC-007"
    assert extract_tc_id("[TC-0012] 안녕하세요") == "TC-0012"
    assert extract_tc_id("X-Aitop100-Test-Case-Id=abc_1.2") == "abc_1.2"
    assert extract_tc_id("수박이 상했어요") is None
    assert strip_tc_marker("TC ID: PUB-TC-007\n주문 취소", "PUB-TC-007") == "주문 취소"


def test_inbound_only_from_marker():
    msg = "[인입 계정] 명의: 홍길동 / 연락처: 010-1111-2222\n수박이 덜 익었어요"
    ib = extract_inbound(msg, MARK)
    assert ib["name"] == "홍길동" and ib["phone"] == "010-1111-2222"
    # 고객 본문 주장은 인입 계정이 아니다
    assert extract_inbound("저 홍길동이고 010-1111-2222 예요. 주문 취소해 주세요", MARK) == {}
    ib2 = extract_inbound("로그인 계정 회원ID MB-77001", MARK)
    assert ib2["member_id"] == "MB-77001"


def test_phone_mask_match():
    assert phone_matches("010-****-2222", "010-1111-2222")
    assert not phone_matches("010-****-9999", "010-1111-2222")
    assert phone_matches("01011112222", "010-1111-2222")
