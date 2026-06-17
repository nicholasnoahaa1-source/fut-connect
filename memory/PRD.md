# Fut Connect — PRD (Plataforma de Talentos Esportivos)

## Original Problem Statement
User uploaded a single-file HTML mockup (`fut-connect-app.html`) — a Brazilian Portuguese sports talent platform connecting **atletas** (athletes) and **técnicos** (coaches). Operating in "modo demonstração" with localStorage. Asked to "melhore e publique-o".

## User Choices (Jan 2026)
- Full-stack: React + FastAPI + MongoDB
- Auth: Google (Emergent) + Email/password with 6-digit code via Gmail SMTP
- Modern redesign + real photo & video uploads + real DB
- IA: Claude Sonnet 4.5 for analysis & recommendations
- Language: **pt-BR**, foco no Brasil

## Architecture
- **Backend**: FastAPI (`/app/backend/server.py`), MongoDB collections: users, user_sessions, email_codes, athletes, coaches, opportunities, applications, favorites, messages, evolution, views
- **Frontend**: React 19 single-page (`/app/frontend/src/App.js`); routes `/` (login/verify) and `/dashboard` (auth-gated)
- **Auth**:
  - Path A: Emergent Google OAuth → `/api/auth/session` → `session_token` cookie (7d)
  - Path B: `/api/auth/signup` (with role) → email code (Gmail SMTP) → `/api/auth/verify` → `session_token` cookie
  - Login: `/api/auth/login`; Forgot/Reset via email code
- **AI**: `emergentintegrations` LiteLLM → Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)
- **Media**:
  - Photos: base64 data URLs (max 2MB) in MongoDB
  - Videos: Cloudinary signed upload (frontend → Cloudinary direct via `/api/upload/sign`) OR YouTube/Drive embed URLs

## Implemented (iter 1 → 3)
- ✅ Google OAuth + role-pick
- ✅ Email/password signup + 6-digit verification code via Gmail SMTP
- ✅ Login + Forgot/Reset password via email code
- ✅ Athlete profile: foto, dados básicos, 9 atributos sliders, vídeos (YouTube/Drive + upload Cloudinary), player card preview, % completude, evolução diária, "quem viu meu perfil"
- ✅ Coach dashboard: clube, ranking destaques, busca avançada, favoritos
- ✅ Public CV view: estatísticas detalhadas, vídeo fixado, ações do técnico (verificar, favoritar, mensagem)
- ✅ Oportunidades (peneiras): técnico publica, atleta candidata
- ✅ IA: análise para atletas + top-3 indicados para técnicos (pt-BR)
- ✅ Seed automático com 4 atletas demo (incl. paralímpico)

## Testing
- Iter 1: 95.6% backend (1 LLM budget issue fixed)
- Iter 2: 100% backend (23/23) + 100% frontend critical flows
- Iter 3: 100% backend (38/38) + 100% frontend (signup, verify, login, forgot/reset, video upload)

## Deployment readiness
- ✅ Checked via deployment_agent — no blockers
- ⚠️ Gmail SMTP credential rejected by Google — user must regenerate app password (see `/app/memory/test_credentials.md`). Codes still readable from `db.email_codes` until fixed.

## Backlog (P1/P2)
- P1: Cleanup of expired email_codes via TTL index
- P2: Sistema de mensagens com inbox/thread completo
- P2: Notificações em tempo real (websocket)
- P2: Slug público para compartilhar currículo
- P2: Stripe — plano "Clube Pro" pra técnicos

## Files
- `/app/backend/server.py` — todos os endpoints
- `/app/frontend/src/App.js` — single-page React
- `/app/frontend/src/index.css` — design system
- `/app/memory/test_credentials.md` — credenciais e instruções de teste
- `/app/auth_testing.md` — playbook de testes de auth
