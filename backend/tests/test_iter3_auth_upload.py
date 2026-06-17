"""Fut Connect — iteration 3 tests: email/password auth, verify, forgot/reset, upload sign."""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://publish-perfected.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="session")
def mongo():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


def _unique_email():
    return f"TEST_{uuid.uuid4().hex[:10]}@example.com".lower()


@pytest.fixture
def fresh_email(mongo):
    email = _unique_email()
    yield email
    # cleanup
    mongo.users.delete_many({"email": email})
    mongo.email_codes.delete_many({"email": email})


# ---------- Signup ----------
class TestSignup:
    def test_signup_valid(self, fresh_email, mongo):
        r = requests.post(f"{API}/auth/signup", json={
            "name": "TEST User", "email": fresh_email, "password": "secret123", "role": "atleta",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert "email_sent" in d
        # code stored in email_codes; no user created yet
        row = mongo.email_codes.find_one({"email": fresh_email, "purpose": "verify"})
        assert row is not None and len(row["code"]) == 6
        u = mongo.users.find_one({"email": fresh_email})
        assert u is None

    def test_signup_short_password(self, fresh_email):
        r = requests.post(f"{API}/auth/signup", json={
            "name": "X", "email": fresh_email, "password": "ab", "role": "atleta",
        })
        assert r.status_code == 400

    def test_signup_existing_verified(self, fresh_email, mongo):
        # seed verified user
        mongo.users.insert_one({
            "user_id": f"u_{uuid.uuid4().hex[:8]}",
            "email": fresh_email,
            "name": "Existing",
            "password_hash": "$2b$12$abcdefghijklmnopqrstuv",
            "verified": True,
            "role": "atleta",
        })
        r = requests.post(f"{API}/auth/signup", json={
            "name": "X", "email": fresh_email, "password": "secret123", "role": "atleta",
        })
        assert r.status_code == 400
        assert "já tem conta" in r.json().get("detail", "")


# ---------- Verify ----------
class TestVerify:
    def test_verify_valid_creates_user(self, fresh_email, mongo):
        # signup first
        r = requests.post(f"{API}/auth/signup", json={
            "name": "TEST Verify", "email": fresh_email, "password": "secret123", "role": "atleta",
        })
        assert r.status_code == 200
        row = mongo.email_codes.find_one({"email": fresh_email, "purpose": "verify"})
        assert row is not None
        code = row["code"]
        # verify
        r2 = requests.post(f"{API}/auth/verify", json={"email": fresh_email, "code": code})
        assert r2.status_code == 200, r2.text
        d = r2.json()
        assert d["ok"] is True
        assert d["user"]["email"] == fresh_email
        assert d["user"]["verified"] is True
        # cookie set
        assert "session_token" in r2.cookies
        # row deleted
        assert mongo.email_codes.find_one({"email": fresh_email, "purpose": "verify"}) is None
        # user exists
        u = mongo.users.find_one({"email": fresh_email})
        assert u is not None and u["verified"] is True

    def test_verify_wrong_code(self, fresh_email):
        requests.post(f"{API}/auth/signup", json={
            "name": "X", "email": fresh_email, "password": "secret123", "role": "atleta",
        })
        r = requests.post(f"{API}/auth/verify", json={"email": fresh_email, "code": "000000"})
        assert r.status_code == 400
        assert "incorreto" in r.json().get("detail", "").lower()

    def test_verify_expired(self, fresh_email, mongo):
        # seed expired
        mongo.email_codes.insert_one({
            "email": fresh_email, "purpose": "verify", "code": "123456",
            "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "pending_name": "X", "pending_password_hash": "$2b$12$xx", "pending_role": "atleta",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        r = requests.post(f"{API}/auth/verify", json={"email": fresh_email, "code": "123456"})
        assert r.status_code == 400
        assert "expirou" in r.json().get("detail", "").lower()


# ---------- Login ----------
class TestLogin:
    def _signup_and_verify(self, email, mongo, password="secret123"):
        requests.post(f"{API}/auth/signup", json={
            "name": "L", "email": email, "password": password, "role": "atleta",
        })
        row = mongo.email_codes.find_one({"email": email, "purpose": "verify"})
        requests.post(f"{API}/auth/verify", json={"email": email, "code": row["code"]})

    def test_login_valid(self, fresh_email, mongo):
        self._signup_and_verify(fresh_email, mongo)
        r = requests.post(f"{API}/auth/login", json={"email": fresh_email, "password": "secret123"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["user"]["email"] == fresh_email
        assert "session_token" in r.cookies

    def test_login_wrong_password(self, fresh_email, mongo):
        self._signup_and_verify(fresh_email, mongo)
        r = requests.post(f"{API}/auth/login", json={"email": fresh_email, "password": "WRONGPASS"})
        assert r.status_code == 401

    def test_login_unverified(self, fresh_email, mongo):
        # Create user with password_hash but verified=False
        import bcrypt
        ph = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode()
        mongo.users.insert_one({
            "user_id": f"u_{uuid.uuid4().hex[:8]}",
            "email": fresh_email, "name": "X",
            "password_hash": ph, "verified": False, "role": "atleta",
        })
        r = requests.post(f"{API}/auth/login", json={"email": fresh_email, "password": "secret123"})
        assert r.status_code == 403


# ---------- Forgot / Reset ----------
class TestForgotReset:
    def test_forgot_no_user_returns_ok(self):
        email = _unique_email()
        r = requests.post(f"{API}/auth/forgot-password", json={"email": email})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_forgot_creates_reset_code(self, fresh_email, mongo):
        # create verified user
        import bcrypt
        ph = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode()
        mongo.users.insert_one({
            "user_id": f"u_{uuid.uuid4().hex[:8]}",
            "email": fresh_email, "name": "X", "password_hash": ph, "verified": True, "role": "atleta",
        })
        r = requests.post(f"{API}/auth/forgot-password", json={"email": fresh_email})
        assert r.status_code == 200
        row = mongo.email_codes.find_one({"email": fresh_email, "purpose": "reset"})
        assert row is not None

    def test_reset_password_flow(self, fresh_email, mongo):
        import bcrypt
        ph = bcrypt.hashpw(b"oldpassword", bcrypt.gensalt()).decode()
        mongo.users.insert_one({
            "user_id": f"u_{uuid.uuid4().hex[:8]}",
            "email": fresh_email, "name": "X", "password_hash": ph, "verified": True, "role": "atleta",
        })
        requests.post(f"{API}/auth/forgot-password", json={"email": fresh_email})
        row = mongo.email_codes.find_one({"email": fresh_email, "purpose": "reset"})
        assert row is not None
        r = requests.post(f"{API}/auth/reset-password", json={
            "email": fresh_email, "code": row["code"], "new_password": "newpass456",
        })
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        # reset row deleted
        assert mongo.email_codes.find_one({"email": fresh_email, "purpose": "reset"}) is None
        # login with new
        r2 = requests.post(f"{API}/auth/login", json={"email": fresh_email, "password": "newpass456"})
        assert r2.status_code == 200


# ---------- Resend ----------
class TestResend:
    def test_resend_after_signup(self, fresh_email, mongo):
        requests.post(f"{API}/auth/signup", json={
            "name": "X", "email": fresh_email, "password": "secret123", "role": "atleta",
        })
        r = requests.post(f"{API}/auth/resend-code", json={"email": fresh_email})
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ---------- Upload sign ----------
class TestUploadSign:
    def test_sign_no_auth(self):
        r = requests.post(f"{API}/upload/sign")
        assert r.status_code == 401

    def test_sign_with_auth(self, mongo):
        uid = f"u_{uuid.uuid4().hex[:8]}"
        token = f"tok_{uuid.uuid4().hex[:12]}"
        mongo.users.insert_one({"user_id": uid, "email": _unique_email(), "name": "X", "role": "atleta"})
        mongo.user_sessions.insert_one({
            "user_id": uid, "session_token": token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            r = requests.post(f"{API}/upload/sign", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, r.text
            d = r.json()
            for key in ("cloud_name", "api_key", "timestamp", "folder", "signature"):
                assert key in d
            assert uid in d["folder"]
            assert isinstance(d["timestamp"], int)
            assert len(d["signature"]) > 10
        finally:
            mongo.users.delete_one({"user_id": uid})
            mongo.user_sessions.delete_many({"user_id": uid})
