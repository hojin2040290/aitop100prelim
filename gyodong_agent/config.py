"""환경 변수 기반 설정. 비밀 값(토큰)은 코드·로그에 남기지 않는다."""
import os
from dataclasses import dataclass, field


def load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    # Action API
    action_base_url: str = "https://gyodong-mall-action.aitop100.org"
    action_token: str = ""
    action_timeout: float = 10.0
    rate_per_minute: int = 95            # 서버 한도 100/60s 보다 약간 낮게
    eval_budget_total: int = 3000        # 평가 누적 한도
    eval_budget_reserve: int = 100       # 이 아래로 남으면 조회 최소화 모드
    per_tc_call_cap: int = 60            # TC 하나에서 쓸 최대 호출 수(안전장치)
    default_tc_id: str = ""              # 대화에 TC ID가 없을 때 쓸 기본값(연습용)

    # LLM (OpenAI 호환: vLLM / SGLang / llama.cpp)
    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "qwen"
    llm_api_key: str = "EMPTY"
    llm_timeout: float = 40.0
    llm_max_tokens: int = 700
    llm_temperature: float = 0.1
    llm_enable_thinking: bool = False
    max_agent_steps: int = 8
    total_deadline_sec: float = 50.0     # 카카오 60초 무응답 전에 반드시 답장

    # Kakao
    kakao_bot_token: str = ""
    kakao_api_base: str = "https://kapi.kakao.com"
    bot_port: int = 9000
    bot_host: str = "127.0.0.1"

    # 세계관 기준 시각(조회 결과에 시각이 없을 때 '오늘'로 쓰는 값)
    world_now: str = "2037-06-30T10:00:00+09:00"

    # 에스컬레이션 lane 값 형식: "lane" → lane 필드에 LANE2_HANDOFF 등, 대상은 reason 앞머리에 기록
    escalation_target_in_reason: bool = True

    # strict: 인입 계정 인증 + 주문 귀속 확인 필수(규정 원칙, 기본값)
    # lenient: 인입 계정 표시가 전혀 없을 때만 주문 귀속 확인을 생략(공개 TC가 인입 계정을 주지 않는 형식일 때 대비)
    auth_mode: str = "strict"

    # 저장소
    db_path: str = "data/agent.sqlite3"
    session_ttl_sec: int = 6 * 3600
    max_history_messages: int = 16
    reply_char_limit: int = 500

    # 인입 계정 헤더를 알아보는 표식(정규식). 고객 본문이 아니라 채널이 붙인 머리말만 인정한다.
    inbound_marker_regex: str = r"(인입\s*계정|로그인\s*(계정|정보|세션)|인증된\s*계정|계정\s*명의|\[시스템\]|\[계정\]|account)"

    extra: dict = field(default_factory=dict)


def get_settings() -> Settings:
    load_env()
    e = os.environ.get
    return Settings(
        action_base_url=e("ACTION_BASE_URL", Settings.action_base_url).rstrip("/"),
        action_token=e("ACTION_TOKEN", ""),
        action_timeout=_float("ACTION_TIMEOUT", 10.0),
        rate_per_minute=_int("ACTION_RATE_PER_MINUTE", 95),
        eval_budget_total=_int("ACTION_EVAL_BUDGET", 3000),
        eval_budget_reserve=_int("ACTION_EVAL_RESERVE", 100),
        per_tc_call_cap=_int("ACTION_PER_TC_CAP", 60),
        default_tc_id=e("DEFAULT_TC_ID", ""),
        llm_base_url=e("LLM_BASE_URL", e("VLLM_URL", Settings.llm_base_url)),
        llm_model=e("LLM_MODEL", e("VLLM_MODEL", "qwen")),
        llm_api_key=e("LLM_API_KEY", "EMPTY"),
        llm_timeout=_float("LLM_TIMEOUT", 40.0),
        llm_max_tokens=_int("LLM_MAX_TOKENS", 700),
        llm_temperature=_float("LLM_TEMPERATURE", 0.1),
        llm_enable_thinking=e("LLM_ENABLE_THINKING", "0") in ("1", "true", "True"),
        max_agent_steps=_int("AGENT_MAX_STEPS", 8),
        total_deadline_sec=_float("AGENT_DEADLINE_SEC", 50.0),
        kakao_bot_token=e("KAKAO_BOT_TOKEN", ""),
        kakao_api_base=e("KAKAO_API_BASE", "https://kapi.kakao.com").rstrip("/"),
        bot_port=_int("BOT_PORT", 9000),
        bot_host=e("BOT_HOST", "127.0.0.1"),
        world_now=e("WORLD_NOW", Settings.world_now),
        escalation_target_in_reason=e("ESCALATION_TARGET_IN_REASON", "1") not in ("0", "false"),
        auth_mode=e("AUTH_MODE", "strict").strip().lower(),
        db_path=e("AGENT_DB_PATH", Settings.db_path),
        session_ttl_sec=_int("SESSION_TTL_SEC", 6 * 3600),
        max_history_messages=_int("MAX_HISTORY_MESSAGES", 16),
        reply_char_limit=_int("REPLY_CHAR_LIMIT", 500),
        inbound_marker_regex=e("INBOUND_MARKER_REGEX", Settings.inbound_marker_regex),
    )
