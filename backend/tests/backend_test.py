"""Fut Connect — backend regression tests (pytest).
Covers: auth, athlete CRUD, coach, search, opportunities, favorites, messages, AI, role-based 403s.
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://publish-perfected.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ---------- Helpers / fixtures ----------
@pytest.fixture(scope="session")
def mongo():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


def _seed_user(mongo, role):
    uid = f"test_{role}_{uuid.uuid4().hex[:8]}"
    token = f"tok_{role}_{uuid.uuid4().hex[:16]}"
    mongo.users.insert_one({
        "user_id": uid,
        "email": f"TEST_{uid}@example.com",
        "name": f"TEST {role}",
        "picture": "",
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.user_sessions.insert_one({
        "user_id": uid,
        "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return uid, token


@pytest.fixture(scope="session")
def athlete(mongo):
    uid, tok = _seed_user(mongo, "atleta")
    yield {"uid": uid, "token": tok, "headers": {"Authorization": f"Bearer {tok}"}}
    mongo.users.delete_one({"user_id": uid})
    mongo.user_sessions.delete_many({"user_id": uid})
    mongo.athletes.delete_many({"user_id": uid})
    mongo.evolution.delete_many({"user_id": uid})


@pytest.fixture(scope="session")
def coach(mongo):
    uid, tok = _seed_user(mongo, "tecnico")
    yield {"uid": uid, "token": tok, "headers": {"Authorization": f"Bearer {tok}"}}
    mongo.users.delete_one({"user_id": uid})
    mongo.user_sessions.delete_many({"user_id": uid})
    mongo.coaches.delete_many({"user_id": uid})


@pytest.fixture(scope="session")
def rolepick_user(mongo):
    uid, tok = _seed_user(mongo, None)
    # clear role
    mongo.users.update_one({"user_id": uid}, {"$set": {"role": None}})
    yield {"uid": uid, "token": tok, "headers": {"Authorization": f"Bearer {tok}"}}
    mongo.users.delete_one({"user_id": uid})
    mongo.user_sessions.delete_many({"user_id": uid})


# ---------- Basic / Auth ----------
class TestRoot:
    def test_root(self):
        r = requests.get(f"{API}/")
        assert r.status_code == 200
        assert r.json() == {"app": "Fut Connect", "ok": True}


class TestAuth:
    def test_session_bad_id(self):
        r = requests.post(f"{API}/auth/session", json={"session_id": "INVALID_BAD_ID_xxxxxxxxxxxx"})
        assert r.status_code == 401

    def test_me_no_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_token(self, athlete):
        r = requests.get(f"{API}/auth/me", headers=athlete["headers"])
        assert r.status_code == 200
        assert r.json()["user_id"] == athlete["uid"]
        assert r.json()["role"] == "atleta"

    def test_role_invalid(self, rolepick_user):
        r = requests.post(f"{API}/auth/role", headers=rolepick_user["headers"], json={"role": "xx"})
        assert r.status_code == 400

    def test_role_valid(self, rolepick_user, mongo):
        r = requests.post(f"{API}/auth/role", headers=rolepick_user["headers"], json={"role": "atleta"})
        assert r.status_code == 200
        assert r.json()["role"] == "atleta"
        u = mongo.users.find_one({"user_id": rolepick_user["uid"]})
        assert u["role"] == "atleta"


# ---------- Athlete ----------
class TestAthlete:
    def test_get_me_empty_defaults(self, athlete):
        r = requests.get(f"{API}/athlete/me", headers=athlete["headers"])
        assert r.status_code == 200
        d = r.json()
        assert d["user_id"] == athlete["uid"]
        assert d["scores"]["overall"] == 70  # default attrs all 70

    def test_save_and_scoring_math(self, athlete):
        attrs = {"vel": 90, "res": 80, "forc": 70, "ctrl": 90, "fin": 80, "pas": 70, "vis": 90, "dec": 80, "pos": 70}
        payload = {
            "name": "TEST Athlete A", "age": 18, "city": "Rio", "sport": "Futebol",
            "position": "Atacante", "height": 178, "weight": 70,
            "attrs": attrs,
            "videos": [{"id": "v1", "title": "gols", "url": "https://www.youtube.com/watch?v=abc", "pinned": True}],
            "photo": "data:image/png;base64,xxx",
        }
        r = requests.put(f"{API}/athlete/me", headers=athlete["headers"], json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        # math: each cat = avg of 3 keys = 80; overall = avg of 80,80,80 = 80
        assert d["scores"]["fisico"] == 80
        assert d["scores"]["tecnico"] == 80
        assert d["scores"]["mental"] == 80
        assert d["scores"]["overall"] == 80

        # GET to verify persistence
        r2 = requests.get(f"{API}/athlete/me", headers=athlete["headers"])
        assert r2.status_code == 200
        assert r2.json()["name"] == "TEST Athlete A"
        assert r2.json()["scores"]["overall"] == 80

    def test_evolution_snapshot(self, athlete):
        r = requests.get(f"{API}/athlete/evolution", headers=athlete["headers"])
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 1
        assert "date" in rows[0] and "overall" in rows[0]

    def test_public_profile_and_view_tracking(self, athlete, coach):
        # coach views athlete profile
        r = requests.get(f"{API}/athletes/{athlete['uid']}", headers=coach["headers"])
        assert r.status_code == 200
        assert r.json()["user_id"] == athlete["uid"]
        # athlete views own visit log
        time.sleep(0.5)
        r2 = requests.get(f"{API}/athlete/views", headers=athlete["headers"])
        assert r2.status_code == 200
        views = r2.json()
        assert any(v["viewer_id"] == coach["uid"] for v in views)


# ---------- Coach ----------
class TestCoach:
    def test_coach_round_trip(self, coach):
        r = requests.put(f"{API}/coach/me", headers=coach["headers"],
                         json={"club": "TEST FC", "city": "Rio", "sport": "Futebol", "category": "Sub-17"})
        assert r.status_code == 200
        r2 = requests.get(f"{API}/coach/me", headers=coach["headers"])
        assert r2.status_code == 200
        assert r2.json()["club"] == "TEST FC"


# ---------- Search ----------
class TestSearch:
    def test_search_seeded(self, coach):
        r = requests.post(f"{API}/athletes/search", headers=coach["headers"], json={"sport": "Futebol"})
        assert r.status_code == 200
        names = [a.get("name") for a in r.json()]
        assert "Lucas Maré" in names

    def test_search_filters_and_sort(self, coach):
        r = requests.post(f"{API}/athletes/search", headers=coach["headers"],
                          json={"sport": "Futebol", "min_overall": 70})
        assert r.status_code == 200
        out = r.json()
        # sorted desc
        overalls = [a["scores"]["overall"] for a in out]
        assert overalls == sorted(overalls, reverse=True)

    def test_highlights(self, coach):
        r = requests.get(f"{API}/athletes/highlights/Futebol", headers=coach["headers"])
        assert r.status_code == 200
        assert len(r.json()) <= 5

    def test_seeded_demos_present(self, coach):
        sports_expected = {
            "Futebol": "Lucas Maré",
            "Basquete": "Bia Armadora",
            "Futebol de 5 (cego)": "Day Paralímpica",
            "Atletismo": "Rafa Veloz",
        }
        for sport, name in sports_expected.items():
            r = requests.post(f"{API}/athletes/search", headers=coach["headers"], json={"sport": sport})
            assert r.status_code == 200, sport
            names = [a.get("name") for a in r.json()]
            assert name in names, f"missing {name} in {sport}: {names}"


# ---------- Favorites ----------
class TestFavorites:
    def test_toggle_and_list(self, coach, athlete):
        r = requests.post(f"{API}/favorites/toggle", headers=coach["headers"],
                          json={"athlete_user_id": athlete["uid"]})
        assert r.status_code == 200 and r.json()["favorited"] is True
        r2 = requests.get(f"{API}/favorites", headers=coach["headers"])
        assert r2.status_code == 200
        assert any(a["user_id"] == athlete["uid"] for a in r2.json())
        r3 = requests.post(f"{API}/favorites/toggle", headers=coach["headers"],
                           json={"athlete_user_id": athlete["uid"]})
        assert r3.json()["favorited"] is False


# ---------- Opportunities + role 403 ----------
class TestOpportunities:
    def test_create_list_apply_delete(self, coach, athlete):
        r = requests.post(f"{API}/opportunities", headers=coach["headers"],
                          json={"title": "TEST Peneira", "sport": "Futebol", "city": "Rio"})
        assert r.status_code == 200
        opp_id = r.json()["id"]

        r2 = requests.get(f"{API}/opportunities", headers=athlete["headers"])
        assert r2.status_code == 200
        assert any(o["id"] == opp_id for o in r2.json())

        # athlete cannot create
        r3 = requests.post(f"{API}/opportunities", headers=athlete["headers"],
                           json={"title": "x", "sport": "Futebol"})
        assert r3.status_code == 403

        # athlete applies
        r4 = requests.post(f"{API}/opportunities/apply", headers=athlete["headers"],
                           json={"opp_id": opp_id, "note": "TEST"})
        assert r4.status_code == 200

        # coach cannot apply
        r5 = requests.post(f"{API}/opportunities/apply", headers=coach["headers"],
                           json={"opp_id": opp_id})
        assert r5.status_code == 403

        # delete
        r6 = requests.delete(f"{API}/opportunities/{opp_id}", headers=coach["headers"])
        assert r6.status_code == 200


# ---------- Messages ----------
class TestMessages:
    def test_send_and_inbox(self, coach, athlete):
        r = requests.post(f"{API}/messages", headers=coach["headers"],
                          json={"to_user_id": athlete["uid"], "text": "TEST oi"})
        assert r.status_code == 200
        r2 = requests.get(f"{API}/messages/inbox", headers=athlete["headers"])
        assert r2.status_code == 200
        assert any(m["text"] == "TEST oi" for m in r2.json())


# ---------- Verify ----------
class TestVerify:
    def test_verify_athlete(self, coach, athlete):
        r = requests.post(f"{API}/athletes/{athlete['uid']}/verify", headers=coach["headers"])
        assert r.status_code == 200
        r2 = requests.get(f"{API}/athletes/{athlete['uid']}", headers=coach["headers"])
        assert r2.json()["verified"] is True

    def test_verify_atleta_forbidden(self, athlete):
        r = requests.post(f"{API}/athletes/{athlete['uid']}/verify", headers=athlete["headers"])
        assert r.status_code == 403


# ---------- AI (Claude Sonnet 4.5) ----------
class TestAI:
    def test_ai_recommend_coach(self, coach):
        r = requests.post(f"{API}/ai/recommend", headers=coach["headers"],
                          json={"sport": "Futebol"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "recommendation" in d and "candidates" in d
        assert "Não consegui gerar agora" not in d["recommendation"], "LLM fallback returned"
        assert len(d["recommendation"]) > 50

    def test_ai_analyze_atleta(self, athlete):
        r = requests.post(f"{API}/ai/analyze", headers=athlete["headers"],
                          json={"focus": "atacante explosivo"}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert "Não consegui gerar agora" not in d["analysis"], "LLM fallback returned"
        assert len(d["analysis"]) > 50

    def test_ai_role_forbidden(self, coach, athlete):
        # atleta cannot recommend
        r = requests.post(f"{API}/ai/recommend", headers=athlete["headers"], json={})
        assert r.status_code == 403
        # coach cannot analyze
        r2 = requests.post(f"{API}/ai/analyze", headers=coach["headers"], json={})
        assert r2.status_code == 403
