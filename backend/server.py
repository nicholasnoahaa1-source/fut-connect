"""Fut Connect — backend
React + FastAPI + MongoDB.
REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
"""
import os
import uuid
import logging
import smtplib
import secrets
import hashlib
import time
import random
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

import httpx
import bcrypt
import cloudinary
import cloudinary.utils
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Cookie, Header
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, field_validator, EmailStr

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

logger = logging.getLogger("futconnect")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Fut Connect API")
api = APIRouter(prefix="/api")


# ---------- Helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def gen_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# Cloudinary config
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
    secure=True,
)


# ---------- Email (Gmail SMTP) ----------
def send_email(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    user = os.environ.get("GMAIL_USER", "").strip()
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    from_name = os.environ.get("EMAIL_FROM_NAME", "Fut Connect")
    if not user or not pwd:
        logger.warning("Gmail SMTP not configured; email NOT sent to %s", to_email)
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{user}>"
        msg["To"] = to_email
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
        logger.info("Sent email to %s | subject=%s", to_email, subject)
        return True
    except Exception as e:
        logger.exception("Email send failed: %s", e)
        return False


def code_email_html(code: str, action: str = "confirmar tua conta") -> tuple[str, str]:
    text = f"Teu codigo Fut Connect: {code}\n\nUse pra {action}. Expira em 10 minutos."
    html = f"""
    <div style="font-family:Manrope,system-ui,sans-serif;background:#0c0b09;color:#f4eee2;padding:32px;border-radius:18px;max-width:480px;margin:auto">
      <div style="font-family:'Anton',sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#ffc23d;font-size:24px">FUT CONNECT</div>
      <h2 style="font-family:'Anton',sans-serif;font-weight:400;letter-spacing:.05em;text-transform:uppercase;color:#fff;margin-top:24px">Teu codigo</h2>
      <p style="color:#b7af9d">Use o codigo abaixo pra {action}:</p>
      <div style="font-family:'Courier New',monospace;font-size:36px;letter-spacing:12px;background:rgba(255,194,61,.13);border:1px solid rgba(255,194,61,.4);color:#ffc23d;border-radius:12px;padding:18px;text-align:center;margin:18px 0;font-weight:700">{code}</div>
      <p style="color:#776f60;font-size:13px">Expira em 10 minutos. Se voce nao pediu isso, ignore este e-mail.</p>
    </div>
    """
    return html, text




async def get_user_from_session(
    session_token_cookie: Optional[str] = Cookie(default=None, alias="session_token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token = session_token_cookie
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    expires_at = sess["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now_utc():
        raise HTTPException(status_code=401, detail="Sessão expirada")
    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user


# ---------- Models ----------
class SessionExchange(BaseModel):
    session_id: str


class SignupPayload(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: Optional[str] = None  # "atleta" | "tecnico"


class VerifyPayload(BaseModel):
    email: EmailStr
    code: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class ForgotPayload(BaseModel):
    email: EmailStr


class ResetPayload(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class RolePick(BaseModel):
    role: str  # "atleta" | "tecnico"


class AthletePayload(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    city: Optional[str] = None
    sport: Optional[str] = "Futebol"
    position: Optional[str] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    dominant: Optional[str] = "Destro"
    history: Optional[str] = None
    bio: Optional[str] = None
    photo: Optional[str] = None  # data URL or http
    videos: Optional[List[Dict[str, Any]]] = None  # [{id,title,url,pinned}]
    attrs: Optional[Dict[str, int]] = None  # vel,res,forc,ctrl,fin,pas,vis,dec,pos

    @field_validator("age", "height", "weight", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class CoachPayload(BaseModel):
    club: Optional[str] = None
    city: Optional[str] = None
    sport: Optional[str] = "Futebol"
    category: Optional[str] = None


class SearchQuery(BaseModel):
    sport: Optional[str] = None
    position: Optional[str] = None
    city: Optional[str] = None
    max_age: Optional[int] = None
    min_height: Optional[int] = None
    only_verified: bool = False
    min_overall: int = 0
    min_fisico: int = 0
    min_tecnico: int = 0
    min_mental: int = 0


class OpportunityPayload(BaseModel):
    title: str
    sport: str = "Futebol"
    category: Optional[str] = None
    city: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None


class ApplicationPayload(BaseModel):
    opp_id: str
    note: Optional[str] = None


class MessagePayload(BaseModel):
    to_user_id: str
    text: str
    about_opp: Optional[str] = None


class FavoritePayload(BaseModel):
    athlete_user_id: str


class AIRecommendPayload(BaseModel):
    sport: Optional[str] = None
    position: Optional[str] = None
    notes: Optional[str] = None


class AIAnalyzePayload(BaseModel):
    focus: Optional[str] = None  # ex: "atacante explosivo"


# ---------- Auth helpers (email/password) ----------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def gen_code() -> str:
    return f"{random.randint(0, 999999):06d}"


async def create_session_for_user(user_id: str, response: Response) -> str:
    token = secrets.token_urlsafe(32)
    expires = now_utc() + timedelta(days=7)
    await db.user_sessions.insert_one(
        {
            "user_id": user_id,
            "session_token": token,
            "expires_at": expires.isoformat(),
            "created_at": now_utc().isoformat(),
        }
    )
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=7 * 24 * 60 * 60,
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )
    return token


# ---------- Auth ----------
@api.get("/")
async def root():
    return {"app": "Fut Connect", "ok": True}


@api.post("/auth/signup")
async def auth_signup(payload: SignupPayload):
    email = payload.email.lower().strip()
    if len(payload.password) < 6:
        raise HTTPException(400, "Senha precisa ter no mínimo 6 caracteres")
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing and existing.get("password_hash"):
        raise HTTPException(400, "Esse e-mail já tem conta. Faça login.")
    code = gen_code()
    expires = now_utc() + timedelta(minutes=10)
    await db.email_codes.update_one(
        {"email": email, "purpose": "verify"},
        {"$set": {
            "email": email, "purpose": "verify", "code": code,
            "expires_at": expires.isoformat(),
            "pending_name": payload.name,
            "pending_password_hash": hash_password(payload.password),
            "pending_role": payload.role,
            "created_at": now_utc().isoformat(),
        }},
        upsert=True,
    )
    html, text = code_email_html(code, "confirmar tua conta")
    sent = send_email(email, "Teu código Fut Connect", html, text)
    return {"ok": True, "email": email, "email_sent": sent}


@api.post("/auth/verify")
async def auth_verify(payload: VerifyPayload, response: Response):
    email = payload.email.lower().strip()
    row = await db.email_codes.find_one({"email": email, "purpose": "verify"}, {"_id": 0})
    if not row:
        raise HTTPException(400, "Código não encontrado. Cadastra de novo.")
    exp = datetime.fromisoformat(row["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now_utc():
        raise HTTPException(400, "Código expirou. Pede outro.")
    if row["code"] != payload.code.strip():
        raise HTTPException(400, "Código incorreto.")
    # create user
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user_id = gen_id("user")
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": row.get("pending_name") or email.split("@")[0],
            "picture": "",
            "role": row.get("pending_role"),
            "password_hash": row.get("pending_password_hash"),
            "verified": True,
            "created_at": now_utc().isoformat(),
        })
    else:
        user_id = user["user_id"]
        await db.users.update_one({"user_id": user_id}, {"$set": {
            "password_hash": row.get("pending_password_hash") or user.get("password_hash"),
            "verified": True,
            "name": row.get("pending_name") or user.get("name"),
            "role": row.get("pending_role") or user.get("role"),
        }})
    await db.email_codes.delete_one({"email": email, "purpose": "verify"})
    await create_session_for_user(user_id, response)
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    return {"user": user_doc, "ok": True}


@api.post("/auth/login")
async def auth_login(payload: LoginPayload, response: Response):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash"):
        raise HTTPException(401, "E-mail ou senha inválidos")
    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "E-mail ou senha inválidos")
    if not user.get("verified"):
        raise HTTPException(403, "Confirma teu e-mail primeiro")
    await create_session_for_user(user["user_id"], response)
    user_doc = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return {"user": user_doc, "ok": True}


@api.post("/auth/resend-code")
async def auth_resend(payload: ForgotPayload):
    email = payload.email.lower().strip()
    row = await db.email_codes.find_one({"email": email, "purpose": "verify"}, {"_id": 0})
    if not row:
        raise HTTPException(400, "Não há cadastro pendente. Faz signup de novo.")
    code = gen_code()
    expires = now_utc() + timedelta(minutes=10)
    await db.email_codes.update_one(
        {"email": email, "purpose": "verify"},
        {"$set": {"code": code, "expires_at": expires.isoformat()}},
    )
    html, text = code_email_html(code, "confirmar tua conta")
    sent = send_email(email, "Teu código Fut Connect", html, text)
    return {"ok": True, "email_sent": sent}


@api.post("/auth/forgot-password")
async def auth_forgot(payload: ForgotPayload):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    # Always return ok to avoid email enumeration
    if not user or not user.get("password_hash"):
        return {"ok": True, "email_sent": False}
    code = gen_code()
    expires = now_utc() + timedelta(minutes=10)
    await db.email_codes.update_one(
        {"email": email, "purpose": "reset"},
        {"$set": {"email": email, "purpose": "reset", "code": code,
                  "expires_at": expires.isoformat(), "created_at": now_utc().isoformat()}},
        upsert=True,
    )
    html, text = code_email_html(code, "recuperar tua senha")
    sent = send_email(email, "Recuperar senha — Fut Connect", html, text)
    return {"ok": True, "email_sent": sent}


@api.post("/auth/reset-password")
async def auth_reset(payload: ResetPayload, response: Response):
    email = payload.email.lower().strip()
    if len(payload.new_password) < 6:
        raise HTTPException(400, "Senha precisa ter no mínimo 6 caracteres")
    row = await db.email_codes.find_one({"email": email, "purpose": "reset"}, {"_id": 0})
    if not row:
        raise HTTPException(400, "Código não encontrado")
    exp = datetime.fromisoformat(row["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now_utc():
        raise HTTPException(400, "Código expirou")
    if row["code"] != payload.code.strip():
        raise HTTPException(400, "Código incorreto")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "verified": True}},
    )
    await db.email_codes.delete_one({"email": email, "purpose": "reset"})
    await create_session_for_user(user["user_id"], response)
    return {"ok": True}


@api.post("/auth/session")
async def auth_session(payload: SessionExchange, response: Response):
    """Exchange Emergent session_id for our session_token. Stores user + session."""
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": payload.session_id},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="session_id inválido")
    data = r.json()
    email = data["email"]
    name = data.get("name") or email.split("@")[0]
    picture = data.get("picture") or ""
    session_token = data["session_token"]

    # upsert user
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture, "updated_at": now_utc().isoformat()}},
        )
    else:
        user_id = gen_id("user")
        await db.users.insert_one(
            {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "role": None,
                "created_at": now_utc().isoformat(),
            }
        )

    # store session (7 days)
    expires = now_utc() + timedelta(days=7)
    await db.user_sessions.update_one(
        {"session_token": session_token},
        {
            "$set": {
                "user_id": user_id,
                "session_token": session_token,
                "expires_at": expires.isoformat(),
                "created_at": now_utc().isoformat(),
            }
        },
        upsert=True,
    )
    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=7 * 24 * 60 * 60,
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": user, "session_token": session_token}


@api.get("/auth/me")
async def me(user=Depends(get_user_from_session)):
    user.pop("password_hash", None)
    return user


@api.post("/auth/logout")
async def logout(response: Response, user=Depends(get_user_from_session)):
    await db.user_sessions.delete_many({"user_id": user["user_id"]})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@api.post("/auth/role")
async def set_role(payload: RolePick, user=Depends(get_user_from_session)):
    if payload.role not in ("atleta", "tecnico"):
        raise HTTPException(status_code=400, detail="Função inválida")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": payload.role}})
    return {"ok": True, "role": payload.role}


# ---------- Cloudinary signed upload ----------
@api.post("/upload/sign")
async def upload_sign(user=Depends(get_user_from_session)):
    """Return signed Cloudinary params so frontend can upload directly.
    Frontend then POSTs the file + these params to
    https://api.cloudinary.com/v1_1/{cloud_name}/auto/upload
    """
    cloud = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    api_key = os.environ.get("CLOUDINARY_API_KEY", "")
    api_secret = os.environ.get("CLOUDINARY_API_SECRET", "")
    if not (cloud and api_key and api_secret):
        raise HTTPException(500, "Cloudinary não configurado")
    ts = int(time.time())
    folder = f"futconnect/{user['user_id']}"
    params_to_sign = {"timestamp": ts, "folder": folder}
    signature = cloudinary.utils.api_sign_request(params_to_sign, api_secret)
    return {
        "cloud_name": cloud,
        "api_key": api_key,
        "timestamp": ts,
        "folder": folder,
        "signature": signature,
    }


# ---------- Attributes / scoring ----------
ALL_KEYS = ["vel", "res", "forc", "ctrl", "fin", "pas", "vis", "dec", "pos"]


def empty_attrs() -> Dict[str, int]:
    return {k: 70 for k in ALL_KEYS}


def cat_scores(a: Dict[str, int]) -> Dict[str, int]:
    a = a or {}

    def avg(ks):
        return round(sum(int(a.get(k, 0)) for k in ks) / len(ks))

    f = avg(["vel", "res", "forc"])
    t = avg(["ctrl", "fin", "pas"])
    m = avg(["vis", "dec", "pos"])
    return {"fisico": f, "tecnico": t, "mental": m, "overall": round((f + t + m) / 3)}


# ---------- Athlete ----------
@api.get("/athlete/me")
async def athlete_me(user=Depends(get_user_from_session)):
    doc = await db.athletes.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        return {
            "user_id": user["user_id"],
            "name": user.get("name"),
            "photo": user.get("picture"),
            "videos": [],
            "attrs": empty_attrs(),
            "verified": False,
            "scores": cat_scores(empty_attrs()),
        }
    doc["scores"] = cat_scores(doc.get("attrs") or empty_attrs())
    return doc


@api.put("/athlete/me")
async def athlete_save(payload: AthletePayload, user=Depends(get_user_from_session)):
    existing = await db.athletes.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
    data = {**existing, **{k: v for k, v in payload.dict().items() if v is not None}}
    data["user_id"] = user["user_id"]
    data.setdefault("name", user.get("name"))
    data.setdefault("verified", False)
    if not data.get("attrs"):
        data["attrs"] = empty_attrs()
    data["updated_at"] = now_utc().isoformat()
    await db.athletes.update_one({"user_id": user["user_id"]}, {"$set": data}, upsert=True)

    # snap evolução (one per day)
    sc = cat_scores(data["attrs"])
    today = now_utc().date().isoformat()
    await db.evolution.update_one(
        {"user_id": user["user_id"], "date": today},
        {"$set": {"user_id": user["user_id"], "date": today, **sc}},
        upsert=True,
    )

    data["scores"] = sc
    return data


@api.get("/athletes/{athlete_id}")
async def athlete_public(athlete_id: str, viewer=Depends(get_user_from_session)):
    doc = await db.athletes.find_one({"user_id": athlete_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, detail="Atleta não encontrado")
    doc["scores"] = cat_scores(doc.get("attrs") or empty_attrs())
    # track view (not self)
    if viewer["user_id"] != athlete_id and viewer.get("role") == "tecnico":
        # de-dup per hour
        recent = await db.views.find_one(
            {"athlete_id": athlete_id, "viewer_id": viewer["user_id"]},
            sort=[("ts", -1)],
            projection={"_id": 0},
        )
        nowts = now_utc().timestamp()
        if not recent or nowts - recent.get("ts", 0) > 3600:
            await db.views.insert_one(
                {
                    "athlete_id": athlete_id,
                    "viewer_id": viewer["user_id"],
                    "viewer_name": viewer.get("name", ""),
                    "ts": nowts,
                }
            )
    return doc


@api.get("/athlete/evolution")
async def athlete_evolution(user=Depends(get_user_from_session)):
    rows = await db.evolution.find({"user_id": user["user_id"]}, {"_id": 0}).sort("date", 1).to_list(500)
    return rows


@api.get("/athlete/views")
async def athlete_views(user=Depends(get_user_from_session)):
    rows = await db.views.find({"athlete_id": user["user_id"]}, {"_id": 0}).sort("ts", -1).to_list(50)
    return rows


@api.post("/athletes/{athlete_id}/verify")
async def verify_athlete(athlete_id: str, user=Depends(get_user_from_session)):
    if user.get("role") != "tecnico":
        raise HTTPException(403, detail="Apenas técnicos podem verificar")
    await db.athletes.update_one({"user_id": athlete_id}, {"$set": {"verified": True}})
    return {"ok": True}


# ---------- Coach ----------
@api.get("/coach/me")
async def coach_me(user=Depends(get_user_from_session)):
    doc = await db.coaches.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return doc or {"user_id": user["user_id"]}


@api.put("/coach/me")
async def coach_save(payload: CoachPayload, user=Depends(get_user_from_session)):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    data["user_id"] = user["user_id"]
    data["updated_at"] = now_utc().isoformat()
    await db.coaches.update_one({"user_id": user["user_id"]}, {"$set": data}, upsert=True)
    return data


@api.post("/athletes/search")
async def search_athletes(q: SearchQuery, user=Depends(get_user_from_session)):
    mongo_q: Dict[str, Any] = {}
    if q.sport:
        mongo_q["sport"] = q.sport
    if q.position:
        mongo_q["position"] = {"$regex": q.position, "$options": "i"}
    if q.city:
        mongo_q["city"] = {"$regex": q.city, "$options": "i"}
    if q.max_age is not None:
        mongo_q["age"] = {"$lte": q.max_age}
    if q.min_height is not None:
        mongo_q["height"] = {"$gte": q.min_height}
    if q.only_verified:
        mongo_q["verified"] = True
    rows = await db.athletes.find(mongo_q, {"_id": 0}).to_list(200)
    out = []
    for r in rows:
        sc = cat_scores(r.get("attrs") or empty_attrs())
        if (
            sc["overall"] >= q.min_overall
            and sc["fisico"] >= q.min_fisico
            and sc["tecnico"] >= q.min_tecnico
            and sc["mental"] >= q.min_mental
        ):
            r["scores"] = sc
            out.append(r)
    out.sort(key=lambda x: x["scores"]["overall"], reverse=True)
    return out


@api.get("/athletes/highlights/{sport}")
async def highlights(sport: str, user=Depends(get_user_from_session)):
    rows = await db.athletes.find({"sport": sport}, {"_id": 0}).to_list(200)
    for r in rows:
        r["scores"] = cat_scores(r.get("attrs") or empty_attrs())
    rows.sort(key=lambda x: x["scores"]["overall"], reverse=True)
    return rows[:5]


# ---------- Favorites ----------
@api.post("/favorites/toggle")
async def fav_toggle(p: FavoritePayload, user=Depends(get_user_from_session)):
    exists = await db.favorites.find_one(
        {"coach_id": user["user_id"], "athlete_id": p.athlete_user_id}, {"_id": 0}
    )
    if exists:
        await db.favorites.delete_one(
            {"coach_id": user["user_id"], "athlete_id": p.athlete_user_id}
        )
        return {"favorited": False}
    await db.favorites.insert_one(
        {"coach_id": user["user_id"], "athlete_id": p.athlete_user_id, "ts": now_utc().isoformat()}
    )
    return {"favorited": True}


@api.get("/favorites")
async def fav_list(user=Depends(get_user_from_session)):
    rows = await db.favorites.find({"coach_id": user["user_id"]}, {"_id": 0}).to_list(200)
    out = []
    for r in rows:
        a = await db.athletes.find_one({"user_id": r["athlete_id"]}, {"_id": 0})
        if a:
            a["scores"] = cat_scores(a.get("attrs") or empty_attrs())
            out.append(a)
    return out


# ---------- Messages ----------
@api.post("/messages")
async def msg_send(p: MessagePayload, user=Depends(get_user_from_session)):
    msg = {
        "id": gen_id("msg"),
        "from_user_id": user["user_id"],
        "from_name": user.get("name"),
        "to_user_id": p.to_user_id,
        "text": p.text,
        "about_opp": p.about_opp,
        "ts": now_utc().isoformat(),
    }
    await db.messages.insert_one(dict(msg))
    return {**msg}


@api.get("/messages/inbox")
async def msg_inbox(user=Depends(get_user_from_session)):
    rows = await db.messages.find(
        {"to_user_id": user["user_id"]}, {"_id": 0}
    ).sort("ts", -1).to_list(100)
    return rows


# ---------- Opportunities ----------
@api.get("/opportunities")
async def opps_list(sport: Optional[str] = None, user=Depends(get_user_from_session)):
    q: Dict[str, Any] = {}
    if sport:
        q["sport"] = sport
    rows = await db.opportunities.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return rows


@api.post("/opportunities")
async def opps_create(p: OpportunityPayload, user=Depends(get_user_from_session)):
    if user.get("role") != "tecnico":
        raise HTTPException(403, "Apenas técnicos publicam oportunidades")
    o = {
        "id": gen_id("opp"),
        "coach_id": user["user_id"],
        "coach_name": user.get("name"),
        **p.dict(),
        "created_at": now_utc().isoformat(),
    }
    await db.opportunities.insert_one(dict(o))
    return {**o}


@api.delete("/opportunities/{opp_id}")
async def opps_delete(opp_id: str, user=Depends(get_user_from_session)):
    await db.opportunities.delete_one({"id": opp_id, "coach_id": user["user_id"]})
    await db.applications.delete_many({"opp_id": opp_id})
    return {"ok": True}


@api.post("/opportunities/apply")
async def opps_apply(p: ApplicationPayload, user=Depends(get_user_from_session)):
    if user.get("role") != "atleta":
        raise HTTPException(403, "Apenas atletas se candidatam")
    a = {
        "id": gen_id("app"),
        "opp_id": p.opp_id,
        "athlete_id": user["user_id"],
        "athlete_name": user.get("name"),
        "note": p.note,
        "status": "pendente",
        "ts": now_utc().isoformat(),
    }
    await db.applications.insert_one(dict(a))
    return {**a}


@api.get("/opportunities/mine/applications")
async def my_apps(user=Depends(get_user_from_session)):
    rows = await db.applications.find(
        {"athlete_id": user["user_id"]}, {"_id": 0}
    ).to_list(200)
    return rows


@api.get("/opportunities/{opp_id}/applications")
async def opps_apps(opp_id: str, user=Depends(get_user_from_session)):
    rows = await db.applications.find({"opp_id": opp_id}, {"_id": 0}).sort("ts", -1).to_list(200)
    return rows


# ---------- AI (Claude Sonnet 4.5 via Emergent LLM) ----------
async def llm_chat(system: str, user_msg: str) -> str:
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = (
            LlmChat(
                api_key=os.environ["EMERGENT_LLM_KEY"],
                session_id=gen_id("ai"),
                system_message=system,
            )
            .with_model("anthropic", "claude-sonnet-4-5-20250929")
        )
        msg = UserMessage(text=user_msg)
        out = await chat.send_message(msg)
        return str(out)
    except Exception as e:
        logger.exception("LLM error: %s", e)
        return "Não consegui gerar agora. Tenta de novo em alguns instantes."


@api.post("/ai/analyze")
async def ai_analyze(p: AIAnalyzePayload, user=Depends(get_user_from_session)):
    if user.get("role") != "atleta":
        raise HTTPException(403, "Disponível para atletas")
    profile = await db.athletes.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
    sc = cat_scores(profile.get("attrs") or empty_attrs())
    prompt = (
        f"Atleta: {profile.get('name','-')}, {profile.get('sport','Futebol')}, "
        f"{profile.get('position','-')}, {profile.get('age','-')} anos, "
        f"{profile.get('city','-')}. Geral {sc['overall']} (F{sc['fisico']}/T{sc['tecnico']}/M{sc['mental']}). "
        f"Foco: {p.focus or 'evoluir'}.\n\n"
        "Em pt-BR breve: 1) 3 pontos fortes; 2) 3 a melhorar; 3) plano semanal (5 dias, frases curtas); "
        "4) dica de vídeo/perfil."
    )
    text = await llm_chat(
        "Você é um treinador esportivo experiente que dá conselhos práticos e motivadores em pt-BR.",
        prompt,
    )
    return {"analysis": text, "scores": sc}


@api.post("/ai/recommend")
async def ai_recommend(p: AIRecommendPayload, user=Depends(get_user_from_session)):
    if user.get("role") != "tecnico":
        raise HTTPException(403, "Disponível para técnicos")
    coach = await db.coaches.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
    q: Dict[str, Any] = {}
    sport = p.sport or coach.get("sport") or "Futebol"
    q["sport"] = sport
    rows = await db.athletes.find(q, {"_id": 0}).to_list(200)
    for r in rows:
        r["scores"] = cat_scores(r.get("attrs") or empty_attrs())
    rows.sort(key=lambda x: x["scores"]["overall"], reverse=True)
    top = rows[:5]
    summary = "\n".join(
        [
            f"- {r.get('name')} | {r.get('position','-')} | {r.get('city','-')} | "
            f"Geral {r['scores']['overall']} F{r['scores']['fisico']}/T{r['scores']['tecnico']}/M{r['scores']['mental']} "
            f"{'✓' if r.get('verified') else '⏳'}"
            for r in top
        ]
    )
    prompt = (
        f"Técnico em {coach.get('city','-')}, esporte {sport}, categoria {coach.get('category','-')}. "
        f"Busca posição '{p.position or 'qualquer'}'. Notas: {p.notes or '-'}.\n"
        f"Candidatos:\n{summary or '(vazio)'}\n\n"
        "Em pt-BR, monte TOP 3 com nome, justificativa breve (1 frase) e 1 pergunta-chave."
    )
    text = await llm_chat(
        "Você é um olheiro/scout esportivo que indica atletas com base em dados objetivos, em pt-BR direto.",
        prompt,
    )
    return {"recommendation": text, "candidates": top}


# ---------- Mount ----------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def seed_demo_athletes():
    """Seed a few demo athletes if collection empty."""
    count = await db.athletes.count_documents({})
    if count > 0:
        return
    demos = [
        {
            "name": "Lucas Maré",
            "age": 16,
            "sport": "Futebol",
            "position": "Ala",
            "city": "Rio de Janeiro",
            "height": 172,
            "weight": 64,
            "dominant": "Canhoto",
            "history": "Club Municipal (2023–24). Peneira Flamengo sub-15.",
            "bio": "Artilheiro do campeonato escolar 2024. Rápido e canhoto.",
            "verified": True,
            "attrs": {"vel": 90, "res": 82, "forc": 78, "ctrl": 92, "fin": 85, "pas": 80, "vis": 88, "dec": 84, "pos": 82},
            "videos": [{"id": "v1", "title": "Compilado de gols 2024", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "pinned": True}],
        },
        {
            "name": "Bia Armadora",
            "age": 17,
            "sport": "Basquete",
            "position": "Armadora",
            "city": "São Gonçalo",
            "height": 175,
            "weight": 66,
            "dominant": "Destra",
            "history": "Liga estudantil RJ. MVP regional 2024.",
            "bio": "Leitura de jogo e passe acima da média.",
            "verified": False,
            "attrs": {"vel": 84, "res": 86, "forc": 72, "ctrl": 88, "fin": 80, "pas": 93, "vis": 95, "dec": 90, "pos": 86},
            "videos": [],
        },
        {
            "name": "Day Paralímpica",
            "age": 15,
            "sport": "Futebol de 5 (cego)",
            "position": "Atacante",
            "city": "Niterói",
            "height": 168,
            "weight": 60,
            "dominant": "Destra",
            "history": "Projeto paralímpico municipal.",
            "bio": "Domínio pelo som excepcional. Talento paralímpico.",
            "verified": True,
            "attrs": {"vel": 80, "res": 84, "forc": 74, "ctrl": 96, "fin": 90, "pas": 82, "vis": 88, "dec": 86, "pos": 84},
            "videos": [],
        },
        {
            "name": "Rafa Veloz",
            "age": 18,
            "sport": "Atletismo",
            "position": "100m / 200m",
            "city": "Belo Horizonte",
            "height": 180,
            "weight": 74,
            "dominant": "Destro",
            "history": "Bicampeão estadual juvenil.",
            "bio": "Explosão e largada são meus diferenciais.",
            "verified": False,
            "attrs": {"vel": 95, "res": 78, "forc": 88, "ctrl": 70, "fin": 60, "pas": 60, "vis": 70, "dec": 78, "pos": 72},
            "videos": [],
        },
    ]
    for d in demos:
        d["user_id"] = gen_id("demo")
        d["created_at"] = now_utc().isoformat()
        await db.athletes.insert_one(d)
    logger.info("Seeded %d demo athletes", len(demos))


@app.on_event("shutdown")
async def shutdown_db():
    client.close()
