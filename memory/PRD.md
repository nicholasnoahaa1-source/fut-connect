# Fut Connect — PRD (Plataforma de Talentos Esportivos)

## Original Problem Statement
User uploaded a single-file HTML mockup (`fut-connect-app.html`) — a Brazilian Portuguese sports talent platform connecting **atletas** (athletes) and **técnicos** (coaches). Operating in "modo demonstração" with localStorage. Asked to "melhore e publique-o" (improve and publish).

## User Choices (Jan 2026)
- (1a) Full-stack: React + FastAPI + MongoDB with real database and login
- (2b) Auth: Emergent Google Auth (social login)
- (3a + 3c) Modern redesign + real photo/video uploads + real DB
- (4a) IA: Claude Sonnet 4.5 for athlete analysis & coach recommendation
- Language: **pt-BR**, foco no Brasil

## Architecture
- **Backend**: FastAPI (`/app/backend/server.py`), MongoDB collections: users, user_sessions, athletes, coaches, opportunities, applications, favorites, messages, evolution, views
- **Frontend**: React 19 single-page (`/app/frontend/src/App.js`) with router for `/` (login) and `/dashboard` (auth-gated views: athlete, coach, CV, opportunities)
- **Auth**: Emergent Google OAuth → backend `/api/auth/session` exchange → httpOnly `session_token` cookie (7 days)
- **AI**: `emergentintegrations` LiteLLM → Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)
- **Media**: Photos as base64 data URLs (max 2MB) in MongoDB. Videos as YouTube/Google Drive embed URLs.

## User Personas
- **Atleta** — adolescente/jovem que quer mostrar talento (vídeos, atributos físicos/técnicos/mentais, evolução)
- **Técnico/clube** — busca jogadores por filtros, recebe indicações de IA, publica peneiras, favorita atletas

## Core Features (implemented Jan 2026)
- Google OAuth login + role-pick (atleta/tecnico)
- Athlete profile: foto, dados básicos, histórico, bio, 9 atributos com sliders, vídeos YouTube/Drive, player card preview com Geral/Físico/Técnico/Mental, % completude, evolução por dia, "quem viu meu perfil"
- Coach dashboard: clube/escola, ranking de destaques por esporte, busca por sport/posição/cidade/idade/altura/verificado/mínimos, favoritos
- Public CV view: estatísticas detalhadas, vídeo fixado, ficha, ações de técnico (verificar ✓, favoritar ♥, mensagem)
- Oportunidades (peneiras/testes): técnico publica, atleta se candidata
- IA: análise de perfil para atleta + top-3 indicados para técnico (Claude Sonnet 4.5 em pt-BR)
- Seed automático com 4 atletas demo (Lucas Maré/Bia/Day Paralímpica/Rafa Veloz)
- Acessibilidade visual: foco gold, fontes Anton/Manrope/Space Mono, ranges acessíveis com hint via "?"

## Testing
- ✅ Iteration 2: 100% backend (23/23 pytest) + 100% critical frontend flows
- Test creds and seed script in `/app/memory/test_credentials.md`

## Backlog / Next Steps (P1/P2)
- P1: Login por e-mail/senha com código de verificação por e-mail (precisa serviço SendGrid/Resend)
- P1: Upload real de vídeo (Cloudinary) — hoje usa link externo (YouTube/Drive)
- P2: Sistema de mensagens com inbox/thread completo
- P2: Notificações em tempo real (websocket)
- P2: Compartilhar currículo público (slug + link)
- P2: Stripe — clubes podem assinar plano premium pra desbloquear filtros avançados de busca

## Deployment Notes
- Frontend `REACT_APP_BACKEND_URL` already configured
- Backend `MONGO_URL`, `DB_NAME`, `EMERGENT_LLM_KEY` in `/app/backend/.env`
- Supervisor manages both processes — hot reload ativo
