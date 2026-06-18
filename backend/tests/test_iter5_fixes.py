"""Iter 5 bug-fix tests:
1) PUT /api/athlete/me accepts decimal height/weight (rounds to int)
2) /auth/signup, /auth/forgot-password, /auth/resend-code return dev_code when SMTP fails
"""
import os
import uuid
import time
import pytest
import requests
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://publish-perfected.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def mongo():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


@pytest.fixture(scope="module")
def athlete(mongo):
    uid = f"test_iter5_ath_{uuid.uuid4().hex[:8]}"
    tok = f"tok_iter5_{uuid.uuid4().hex[:16]}"
    mongo.users.insert_one({
        "user_id": uid, "email": f"TEST_{uid}@example.com",
        "name": "TEST iter5 Athlete", "role": "atleta",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.user_sessions.insert_one({
        "user_id": uid, "session_token": tok,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield {"uid": uid, "headers": {"Authorization": f"Bearer {tok}"}}
    mongo.users.delete_one({"user_id": uid})
    mongo.user_sessions.delete_many({"user_id": uid})
    mongo.athletes.delete_many({"user_id": uid})
    mongo.evolution.delete_many({"user_id": uid})


# ----- Bug fix #1: decimal height/weight -----
class TestDecimalCoercion:
    def test_put_athlete_with_float_height_weight(self, athlete):
        """Nicholas Noah's exact payload: 189.5 cm, 88.3 kg"""
        r = requests.put(f"{API}/athlete/me", headers=athlete["headers"],
                         json={"name": "TEST Noah", "height": 189.5, "weight": 88.3})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        d = r.json()
        # 189.5 should round to 190 (banker's), 88.3 -> 88
        assert d["height"] == 190, f"height={d['height']}"
        assert d["weight"] == 88, f"weight={d['weight']}"

    def test_put_athlete_with_string_decimal(self, athlete):
        r = requests.put(f"{API}/athlete/me", headers=athlete["headers"],
                         json={"height": "180.7", "weight": "75.4"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["height"] == 181
        assert d["weight"] == 75

    def test_put_athlete_with_int(self, athlete):
        r = requests.put(f"{API}/athlete/me", headers=athlete["headers"],
                         json={"height": 175, "weight": 70})
        assert r.status_code == 200
        d = r.json()
        assert d["height"] == 175
        assert d["weight"] == 70

    def test_put_athlete_with_empty_string(self, athlete):
        # Empty string should coerce to None (not 422)
        r = requests.put(f"{API}/athlete/me", headers=athlete["headers"],
                         json={"height": "", "weight": "", "age": ""})
        assert r.status_code == 200


# ----- Bug fix #2: dev_code fallback when SMTP broken -----
class TestDevCodeFallback:
    @pytest.fixture(autouse=True)
    def _cleanup(self, mongo):
        yield
        mongo.email_codes.delete_many({"email": {"$regex": "^TEST_iter5_"}})
        mongo.users.delete_many({"email": {"$regex": "^TEST_iter5_"}})

    def test_signup_returns_dev_code(self, mongo):
        email = f"TEST_iter5_signup_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/auth/signup", json={
            "name": "TEST Signup", "email": email, "password": "test123",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["email"] == email.lower()
        # Gmail SMTP intentionally broken -> email_sent=False -> dev_code present
        if not d["email_sent"]:
            assert "dev_code" in d, f"Expected dev_code when email_sent=False; got {d}"
            assert isinstance(d["dev_code"], str)
            assert len(d["dev_code"]) == 6
            assert d["dev_code"].isdigit()
            # Verify code matches DB
            row = mongo.email_codes.find_one({"email": email.lower(), "purpose": "verify"})
            assert row and row["code"] == d["dev_code"]

    def test_resend_returns_dev_code(self, mongo):
        email = f"TEST_iter5_resend_{uuid.uuid4().hex[:6]}@example.com"
        # First create a pending signup
        requests.post(f"{API}/auth/signup", json={
            "name": "TEST", "email": email, "password": "test123",
        })
        r = requests.post(f"{API}/auth/resend-code", json={"email": email})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        if not d["email_sent"]:
            assert "dev_code" in d
            assert len(d["dev_code"]) == 6

    def test_forgot_password_returns_dev_code(self, mongo):
        # Need an existing user with password
        email = f"TEST_iter5_forgot_{uuid.uuid4().hex[:6]}@example.com"
        # Signup
        sr = requests.post(f"{API}/auth/signup", json={
            "name": "TEST Forgot", "email": email, "password": "test123",
        })
        code = sr.json().get("dev_code")
        if code:
            requests.post(f"{API}/auth/verify", json={"email": email, "code": code})
        # Now request forgot password
        r = requests.post(f"{API}/auth/forgot-password", json={"email": email})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        if not d["email_sent"]:
            assert "dev_code" in d, f"Expected dev_code; got {d}"
            assert len(d["dev_code"]) == 6

    def test_forgot_unknown_email_no_dev_code(self):
        # Avoid email enumeration: unknown email should not leak dev_code
        r = requests.post(f"{API}/auth/forgot-password",
                          json={"email": f"nonexistent_{uuid.uuid4().hex[:6]}@example.com"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "dev_code" not in d  # no leak
