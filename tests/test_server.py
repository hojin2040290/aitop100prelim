import os
import time

os.environ.setdefault("AGENT_DB_PATH", ":memory:")
os.environ["AUDIT_LOG"] = "/tmp/gyodong_test_audit.jsonl"
os.environ["ADMIN_TOKEN"] = "adm"

from fastapi.testclient import TestClient  # noqa: E402

from gyodong_agent import server  # noqa: E402
from gyodong_agent.agent import TurnResult  # noqa: E402


class SlowAgent:
    def __init__(self):
        self.calls = []

    async def handle(self, conv, text):
        self.calls.append((conv, text))
        return TurnResult(answer="답변", tc_id="T", steps=1)


def test_webhook_acks_fast_and_dedups(monkeypatch):
    sent = []

    async def fake_cb(token, text):
        sent.append((token, text))
        return 200, "ok"

    monkeypatch.setattr(server, "_kakao_callback", fake_cb)
    with TestClient(server.app) as c:
        server.app.state.agent = SlowAgent()
        ev = {"op": "DISPATCH", "d": {"callbackToken": "cbt-1", "botUserKey": "u1", "content": "안녕하세요"}}
        t0 = time.time()
        r = c.post("/kakao/webhook", json=ev)
        assert r.status_code == 200 and time.time() - t0 < 1.0
        r2 = c.post("/kakao/webhook", json=ev)
        assert r2.json().get("duplicate")
        time.sleep(0.3)
        assert sent and sent[0] == ("cbt-1", "답변")
        assert c.post("/kakao/webhook", content=b"not json").status_code == 200
        h = c.get("/health").json()
        assert h["ok"]


def test_chat_requires_admin_token():
    with TestClient(server.app) as c:
        server.app.state.agent = SlowAgent()
        assert c.post("/chat", json={"text": "x"}).status_code == 403
        r = c.post("/chat", json={"text": "x"}, headers={"X-Admin-Token": "adm"})
        assert r.json()["answer"] == "답변"


def test_openbuilder_skill_callback(monkeypatch):
    with TestClient(server.app) as c:
        server.app.state.agent = SlowAgent()
        r = c.post("/kakao/webhook", json={"userRequest": {"utterance": "안녕", "user": {"id": "u9"}}})
        assert r.json()["template"]["outputs"][0]["simpleText"]["text"] == "답변"
