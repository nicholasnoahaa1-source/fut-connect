# Fut Connect — PRD (Plataforma de Talentos Esportivos)

## Original Problem Statement
HTML mockup `fut-connect-app.html` — plataforma esportiva pt-BR conectando atletas e técnicos. Pedido: "melhore e publique-o".

## User Choices (Jan 2026)
- Full-stack React + FastAPI + MongoDB
- Login Google + Email/senha com código (Gmail SMTP)
- Photo + video upload (Cloudinary)
- AI Claude Sonnet 4.5 pra análise/recomendação
- Chat real entre técnicos e atletas
- pt-BR

## Architecture
- **Backend**: FastAPI (`/app/backend/server.py`), collections: users, user_sessions, email_codes, athletes, coaches, opportunities, applications, favorites, messages, evolution, views
- **Frontend**: React 19 single-page (`/app/frontend/src/App.js`)
- **Auth dual**:
  - Path A: Emergent Google OAuth → `session_token` cookie
  - Path B: Signup → email 6-digit code → verify → cookie
  - Dev fallback: quando Gmail SMTP falha, código aparece em modal na UI
- **AI**: emergentintegrations + Claude Sonnet 4.5
- **Upload**: Cloudinary signed upload (backend assina, frontend manda direto)

## Implemented (Iter 1 → 5)
- ✅ Google OAuth + role-pick
- ✅ Email/password signup com verificação por código (+ dev fallback)
- ✅ Forgot/Reset password com código
- ✅ Athlete: perfil, fotos, 9 atributos sliders, vídeos (link OU upload Cloudinary), player card preview, evolução, "quem viu meu perfil"
- ✅ Coach: clube, ranking destaques, busca avançada, favoritos
- ✅ CV público + ações (verificar, favoritar, conversar)
- ✅ Oportunidades (peneiras): técnico publica, atleta candidata
- ✅ AI: análise atleta + top-3 indicações técnico
- ✅ **Chat real-time** técnico ↔ atleta com unread badge, threads, polling 6-12s
- ✅ Aceita decimais em altura/peso (arredonda automaticamente)
- ✅ 4 atletas demo seedados no startup

## Testing
- Iter 1: 95.6% backend
- Iter 2: 100% backend (23/23)
- Iter 3: 100% backend (38/38)
- Iter 4: 100% (chat — 11/11 + 38/38 regression)
- Iter 5: 100% backend (8/8 + 49/49 regression) + 100% frontend

## ⚠️ Known issue
- Gmail SMTP credential rejeitado pelo Google (535 BadCredentials). Workaround: dev_code aparece na UI. Pra resolver: usuário precisa regenerar app password em https://myaccount.google.com/apppasswords

## Backlog (P2)
- Inbox de mensagens com thread (já tem chat, mas falta resumo)
- Notificações push real-time (websocket)
- Slug público pra compartilhar currículo
- Stripe — plano "Clube Pro"
- Refator: server.py e App.js ficaram grandes (>1k linhas)

## Deploy
- Checked via deployment_agent — sem blockers
- Pronto pro botão Deploy
