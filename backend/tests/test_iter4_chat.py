"""Backend tests for Iter 4 - Chat between coaches and athletes."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://publish-perfected.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def users():
    """Create fresh coach + athlete via mongosh-equivalent: directly via signup is not idempotent,
    so we rely on pre-seeded users that the test script inserts.
    We'll create new ones each run with timestamp suffix using direct mongo insertion via the API is not possible;
    so we use bash-side seeding (done by test runner). Fallback: skip if env vars missing.
    """
    # We seed in conftest-like step here, but since the testing agent created users via mongosh,
    # we read them from env or just re-seed inline using a helper subprocess.
    import subprocess, json
    ts = int(time.time() * 1000)
    coach_id = f"tec_pyt_{ts}"
    coach_tok = f"ctokpyt_{ts}"
    ath_id = f"ath_pyt_{ts}"
    ath_tok = f"atokpyt_{ts}"
    script = f"""
db.users.insertOne({{user_id:'{coach_id}', email:'coach.pyt{ts}@test.com', name:'Coach Pyt', role:'tecnico', verified:true, created_at:new Date()}});
db.user_sessions.insertOne({{user_id:'{coach_id}', session_token:'{coach_tok}', expires_at:new Date(Date.now()+7*24*60*60*1000)}});
db.users.insertOne({{user_id:'{ath_id}', email:'atleta.pyt{ts}@test.com', name:'Atleta Pyt', role:'atleta', verified:true, created_at:new Date()}});
db.user_sessions.insertOne({{user_id:'{ath_id}', session_token:'{ath_tok}', expires_at:new Date(Date.now()+7*24*60*60*1000)}});
db.athletes.insertOne({{user_id:'{ath_id}', athlete_id:'apyt_{ts}', name:'Atleta Pyt', sport:'Futebol', city:'Rio', photo:'', verified:true}});
"""
    subprocess.run(["mongosh", "test_database", "--quiet", "--eval", script], check=True, capture_output=True)
    yield {
        "coach_id": coach_id, "coach_tok": coach_tok,
        "ath_id": ath_id, "ath_tok": ath_tok,
    }
    # Cleanup
    cleanup = f"""
db.users.deleteMany({{user_id:{{$in:['{coach_id}','{ath_id}']}}}});
db.user_sessions.deleteMany({{user_id:{{$in:['{coach_id}','{ath_id}']}}}});
db.athletes.deleteMany({{user_id:'{ath_id}'}});
db.messages.deleteMany({{$or:[{{from_user_id:'{coach_id}'}},{{from_user_id:'{ath_id}'}},{{to_user_id:'{coach_id}'}},{{to_user_id:'{ath_id}'}}]}});
"""
    subprocess.run(["mongosh", "test_database", "--quiet", "--eval", cleanup], capture_output=True)


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- Auth gating ----------
class TestAuthGating:
    def test_messages_post_requires_auth(self):
        r = requests.post(f"{API}/messages", json={"to_user_id": "x", "text": "hi"})
        assert r.status_code == 401

    def test_conversations_requires_auth(self):
        r = requests.get(f"{API}/conversations")
        assert r.status_code == 401

    def test_thread_requires_auth(self):
        r = requests.get(f"{API}/messages/thread/someuser")
        assert r.status_code == 401


# ---------- Send / receive ----------
class TestMessageFlow:
    def test_coach_sends_to_athlete(self, users):
        r = requests.post(f"{API}/messages",
                          json={"to_user_id": users["ath_id"], "text": "Olá, sou tecnico"},
                          headers=H(users["coach_tok"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["from_user_id"] == users["coach_id"]
        assert data["to_user_id"] == users["ath_id"]
        assert data["text"] == "Olá, sou tecnico"
        assert data["from_role"] == "tecnico"
        assert data["read"] is False
        assert "id" in data and "ts" in data

    def test_athlete_sends_to_coach(self, users):
        r = requests.post(f"{API}/messages",
                          json={"to_user_id": users["coach_id"], "text": "Oi treinador!"},
                          headers=H(users["ath_tok"]))
        assert r.status_code == 200
        data = r.json()
        assert data["from_role"] == "atleta"
        assert data["read"] is False

    def test_conversations_for_coach(self, users):
        # Should see the athlete as a conversation, with last_text from athlete (most recent)
        r = requests.get(f"{API}/conversations", headers=H(users["coach_tok"]))
        assert r.status_code == 200
        convs = r.json()
        match = [c for c in convs if c["other_user_id"] == users["ath_id"]]
        assert len(match) == 1, f"Expected exactly 1 convo, got {convs}"
        c = match[0]
        assert c["other_name"] == "Atleta Pyt"
        assert c["other_role"] == "atleta"
        assert c["last_text"] == "Oi treinador!"
        assert c["last_from_me"] is False  # athlete sent last msg
        assert c["unread"] >= 1  # athlete's msg unread by coach
        assert "last_ts" in c

    def test_conversations_for_athlete(self, users):
        r = requests.get(f"{API}/conversations", headers=H(users["ath_tok"]))
        assert r.status_code == 200
        convs = r.json()
        match = [c for c in convs if c["other_user_id"] == users["coach_id"]]
        assert len(match) == 1
        c = match[0]
        assert c["other_role"] == "tecnico"
        assert c["last_from_me"] is True  # athlete sent last
        # Athlete never opened thread, so coach's initial msg remains unread for athlete
        assert c["unread"] >= 1

    def test_thread_returns_sorted_messages(self, users):
        r = requests.get(f"{API}/messages/thread/{users['ath_id']}", headers=H(users["coach_tok"]))
        assert r.status_code == 200
        body = r.json()
        assert "messages" in body and "other" in body
        msgs = body["messages"]
        assert len(msgs) >= 2
        # sorted ascending by ts
        timestamps = [m["ts"] for m in msgs]
        assert timestamps == sorted(timestamps)
        assert body["other"]["user_id"] == users["ath_id"]
        assert body["other"]["role"] == "atleta"
        # password_hash excluded
        assert "password_hash" not in body["other"]

    def test_thread_marks_inbound_as_read(self, users):
        # Coach just GET-thread above; now coach's unread should be 0
        time.sleep(0.3)
        r = requests.get(f"{API}/conversations", headers=H(users["coach_tok"]))
        assert r.status_code == 200
        match = [c for c in r.json() if c["other_user_id"] == users["ath_id"]]
        assert match and match[0]["unread"] == 0, f"Expected unread=0 after reading thread, got {match}"

    def test_thread_is_bidirectional_filtered(self, users):
        # Create a third user and send a message coach -> third; this msg must NOT appear in coach<->athlete thread
        import subprocess, time as _t
        ts = int(_t.time() * 1000)
        third_id = f"third_pyt_{ts}"
        third_tok = f"thirdtok_{ts}"
        script = f"""
db.users.insertOne({{user_id:'{third_id}', email:'third{ts}@test.com', name:'Third', role:'atleta', verified:true}});
db.user_sessions.insertOne({{user_id:'{third_id}', session_token:'{third_tok}', expires_at:new Date(Date.now()+7*24*60*60*1000)}});
"""
        subprocess.run(["mongosh", "test_database", "--quiet", "--eval", script], check=True, capture_output=True)
        # coach -> third
        r = requests.post(f"{API}/messages",
                          json={"to_user_id": third_id, "text": "secret to third"},
                          headers=H(users["coach_tok"]))
        assert r.status_code == 200
        # athlete fetches thread with coach — should NOT see "secret to third"
        r2 = requests.get(f"{API}/messages/thread/{users['coach_id']}", headers=H(users["ath_tok"]))
        assert r2.status_code == 200
        texts = [m["text"] for m in r2.json()["messages"]]
        assert "secret to third" not in texts
        # all msgs should be between coach<->ath
        for m in r2.json()["messages"]:
            pair = {m["from_user_id"], m["to_user_id"]}
            assert pair == {users["coach_id"], users["ath_id"]}, f"Stray msg: {m}"
        # cleanup
        cleanup = f"""
db.users.deleteOne({{user_id:'{third_id}'}});
db.user_sessions.deleteOne({{user_id:'{third_id}'}});
db.messages.deleteMany({{$or:[{{from_user_id:'{third_id}'}},{{to_user_id:'{third_id}'}}]}});
"""
        subprocess.run(["mongosh", "test_database", "--quiet", "--eval", cleanup], capture_output=True)

    def test_conversations_sorted_by_last_ts_desc(self, users):
        # send another message coach -> ath to bump the timestamp
        time.sleep(0.05)
        requests.post(f"{API}/messages",
                      json={"to_user_id": users["ath_id"], "text": "newest"},
                      headers=H(users["coach_tok"]))
        r = requests.get(f"{API}/conversations", headers=H(users["coach_tok"]))
        assert r.status_code == 200
        convs = r.json()
        if len(convs) > 1:
            ts_list = [c["last_ts"] for c in convs]
            assert ts_list == sorted(ts_list, reverse=True)
