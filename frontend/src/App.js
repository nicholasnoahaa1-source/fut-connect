import React, { useEffect, useState, useCallback, useMemo } from "react";
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import "@/App.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API, withCredentials: true });

// ===== Helpers =====
const SPORTS = ["Futebol", "Futebol de 5 (cego)", "Basquete", "Goalball", "Atletismo", "Natação", "Vôlei", "Vôlei sentado", "Outro"];
const ATTR_CATS = [
  { name: "Físico", attrs: [
    { k: "vel", label: "Velocidade", tip: "Corra 20m no cronômetro. Mais rápido = nota maior." },
    { k: "res", label: "Resistência", tip: "Quanto tempo segura ritmo forte (teste de 12 min)." },
    { k: "forc", label: "Força / impulsão", tip: "Salto vertical, flexões, potência." },
  ]},
  { name: "Técnico", attrs: [
    { k: "ctrl", label: "Controle / domínio", tip: "Domínio sob pressão — recepção, primeiro toque." },
    { k: "fin", label: "Finalização", tip: "De 10 tentativas ao gol/cesta, quantas acerta?" },
    { k: "pas", label: "Passe", tip: "Porcentagem de passes certos." },
  ]},
  { name: "Mental", attrs: [
    { k: "vis", label: "Visão de jogo", tip: "Enxerga a jogada antes? Assistências." },
    { k: "dec", label: "Decisão", tip: "Sob pressão escolhe certo." },
    { k: "pos", label: "Posicionamento", tip: "Lugar certo na hora certa." },
  ]},
];
const ALL_KEYS = ["vel", "res", "forc", "ctrl", "fin", "pas", "vis", "dec", "pos"];
const emptyAttrs = () => Object.fromEntries(ALL_KEYS.map(k => [k, 70]));

function embedUrl(url) {
  if (!url) return null;
  const yt = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([\w-]{6,})/);
  if (yt) return { type: "iframe", src: `https://www.youtube.com/embed/${yt[1]}` };
  const dr = url.match(/drive\.google\.com\/file\/d\/([\w-]+)/);
  if (dr) return { type: "iframe", src: `https://drive.google.com/file/d/${dr[1]}/preview` };
  // Direct video file (Cloudinary etc.)
  if (/\.(mp4|webm|mov|m4v|ogg)(\?|$)/i.test(url) || url.includes("res.cloudinary.com")) return { type: "video", src: url };
  return null;
}

function rankFor(l) { if (l >= 90) return "Craque"; if (l >= 80) return "Revelação"; if (l >= 65) return "Destaque"; return "Base"; }
function initials(s) { return (s || "").split(" ").filter(Boolean).slice(0, 2).map(p => p[0]).join("").toUpperCase() || "?"; }

// ===== Toast =====
const ToastCtx = React.createContext(() => {});
function ToastProvider({ children }) {
  const [t, setT] = useState(null);
  const push = useCallback((msg) => {
    setT(msg); setTimeout(() => setT(null), 2300);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      {t && <div className="toast" data-testid="toast">{t}</div>}
    </ToastCtx.Provider>
  );
}

// ===== Topbar =====
function Topbar({ user, onLogout, onGoOpps, onGoChat, unread }) {
  return (
    <div className="topbar">
      <div className="topbar-in">
        <div className="logo" data-testid="logo"><span className="dot"></span>FUT CONNECT</div>
        <div className="bar-right">
          {user && (
            <>
              <span className="who">Olá, <b>{user.name?.split(" ")[0] || "atleta"}</b></span>
              {user.role && <span className={`role-badge ${user.role === "tecnico" ? "coach" : ""}`}>{user.role}</span>}
              <button className="btn btn-ghost btn-sm" onClick={onGoChat} data-testid="nav-chat-btn" style={{ position: "relative" }}>
                💬 Mensagens
                {unread > 0 && <span style={{ position: "absolute", top: -4, right: -4, background: "var(--gold)", color: "#1a1205", borderRadius: "100px", fontSize: ".64rem", fontWeight: 800, padding: "2px 6px", lineHeight: 1 }} data-testid="chat-unread-badge">{unread}</span>}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={onGoOpps} data-testid="nav-opps-btn">Oportunidades</button>
              <button className="btn btn-ghost btn-sm" onClick={onLogout} data-testid="logout-btn">Sair</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ===== Login (tabs: Google + Email) =====
function LoginView({ toast, onSignedIn, onNeedVerify }) {
  const [tab, setTab] = useState("login"); // login | signup
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "atleta" });
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);
  const [forgotStep, setForgotStep] = useState(1);
  const [forgotData, setForgotData] = useState({ email: "", code: "", new_password: "" });

  const goGoogle = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const doSignup = async () => {
    if (!form.name.trim() || !form.email.trim() || form.password.length < 6) {
      toast("Preenche nome, e-mail e senha (mín 6)"); return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/auth/signup", form);
      if (data.dev_code) {
        toast(`Código (e-mail offline): ${data.dev_code}`);
        onNeedVerify(form.email, data.dev_code);
      } else {
        toast("Código enviado! Confere teu e-mail 📧");
        onNeedVerify(form.email, null);
      }
    } catch (e) {
      toast(e.response?.data?.detail || "Erro no cadastro");
    }
    setBusy(false);
  };

  const doLogin = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/auth/login", { email: form.email, password: form.password });
      onSignedIn(data.user);
    } catch (e) {
      const msg = e.response?.data?.detail || "Erro no login";
      if (e.response?.status === 403) {
        toast("Confirma teu e-mail primeiro 📧");
        try {
          const { data } = await api.post("/auth/resend-code", { email: form.email });
          onNeedVerify(form.email, data?.dev_code || null);
        } catch (err) {
          onNeedVerify(form.email, null);
        }
      } else {
        toast(msg);
      }
    }
    setBusy(false);
  };

  const doForgot = async () => {
    setBusy(true);
    try {
      if (forgotStep === 1) {
        const { data } = await api.post("/auth/forgot-password", { email: forgotData.email });
        if (data?.dev_code) {
          setForgotData(prev => ({ ...prev, code: data.dev_code }));
          toast(`Código (e-mail offline): ${data.dev_code}`);
        } else {
          toast("Se o e-mail existir, mandamos um código");
        }
        setForgotStep(2);
      } else {
        await api.post("/auth/reset-password", forgotData);
        toast("Senha trocada! Já tá logado 🔓");
        const { data } = await api.get("/auth/me");
        onSignedIn(data);
      }
    } catch (e) {
      toast(e.response?.data?.detail || "Erro");
    }
    setBusy(false);
  };

  if (forgot) {
    return (
      <div className="shell">
        <div className="card-auth">
          <h1 className="display">Recuperar senha</h1>
          <p className="sub">{forgotStep === 1 ? "Coloca teu e-mail. Mandamos um código." : "Digite o código + nova senha."}</p>
          {forgotStep === 1 ? (
            <div className="field"><label>E-mail</label><input type="email" value={forgotData.email} onChange={e => setForgotData({ ...forgotData, email: e.target.value })} data-testid="forgot-email-input" /></div>
          ) : (
            <>
              <div className="field"><label>Código (6 dígitos)</label><input type="text" value={forgotData.code} onChange={e => setForgotData({ ...forgotData, code: e.target.value })} maxLength={6} data-testid="forgot-code-input" /></div>
              <div className="field"><label>Nova senha</label><input type="password" value={forgotData.new_password} onChange={e => setForgotData({ ...forgotData, new_password: e.target.value })} data-testid="forgot-newpass-input" /></div>
            </>
          )}
          <button className="btn btn-gold btn-block" onClick={doForgot} disabled={busy} data-testid="forgot-submit-btn">{busy ? "..." : (forgotStep === 1 ? "Enviar código" : "Trocar senha")}</button>
          <p style={{ textAlign: "center", marginTop: ".7rem" }}><span className="link" onClick={() => { setForgot(false); setForgotStep(1); }}>← Voltar</span></p>
        </div>
      </div>
    );
  }

  return (
    <div className="shell">
      <div className="card-auth">
        <div style={{ fontFamily: "'Space Mono', monospace", fontSize: ".7rem", letterSpacing: ".2em", textTransform: "uppercase", color: "var(--gold)" }}>Plataforma de talentos</div>
        <h1 className="display">Entra na Fut Connect</h1>
        <p className="sub">Atletas mostram o talento. Técnicos acham o jogador certo.</p>

        <button className="btn btn-gold btn-block" onClick={goGoogle} data-testid="google-login-btn" style={{ marginBottom: ".8rem" }}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M21.35 11.1H12v2.9h5.35c-.23 1.24-1.48 3.65-5.35 3.65-3.22 0-5.85-2.66-5.85-5.95s2.63-5.95 5.85-5.95c1.84 0 3.06.78 3.77 1.45l2.57-2.48C16.86 3.27 14.66 2.2 12 2.2 6.96 2.2 2.85 6.31 2.85 11.7c0 5.39 4.11 9.5 9.15 9.5 5.28 0 8.78-3.71 8.78-8.93 0-.6-.07-1.05-.13-1.17z"/></svg>
          Entrar com Google
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: ".7rem", margin: "1.2rem 0", color: "var(--text-faint)", fontSize: ".75rem" }}>
          <div style={{ flex: 1, height: 1, background: "var(--line)" }}></div>OU<div style={{ flex: 1, height: 1, background: "var(--line)" }}></div>
        </div>

        <div className="auth-tabs" style={{ display: "flex", gap: ".4rem", background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: "100px", padding: ".3rem", marginBottom: "1.2rem" }}>
          <button className={`tab-btn ${tab === "login" ? "active" : ""}`} onClick={() => setTab("login")} data-testid="login-tab" style={tabStyle(tab === "login")}>Entrar</button>
          <button className={`tab-btn ${tab === "signup" ? "active" : ""}`} onClick={() => setTab("signup")} data-testid="signup-tab" style={tabStyle(tab === "signup")}>Criar conta</button>
        </div>

        {tab === "signup" && (
          <>
            <div className="field"><label>Nome</label><input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Lucas Silva" data-testid="signup-name-input" /></div>
            <div className="role-pick" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem", marginBottom: ".95rem" }}>
              <button className={`role-opt ${form.role === "atleta" ? "sel" : ""}`} onClick={() => setForm({ ...form, role: "atleta" })} data-testid="signup-role-atleta" type="button"><b>Sou atleta</b><small>Busco oportunidades</small></button>
              <button className={`role-opt ${form.role === "tecnico" ? "sel" : ""}`} onClick={() => setForm({ ...form, role: "tecnico" })} data-testid="signup-role-tecnico" type="button"><b>Sou técnico</b><small>Busco jogadores</small></button>
            </div>
          </>
        )}
        <div className="field"><label>E-mail</label><input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="voce@email.com" data-testid="email-input" /></div>
        <div className="field"><label>Senha</label><input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} placeholder="••••••••" data-testid="password-input" /></div>
        {tab === "login" ? (
          <button className="btn btn-gold btn-block" onClick={doLogin} disabled={busy} data-testid="login-submit-btn">{busy ? "..." : "Entrar"}</button>
        ) : (
          <button className="btn btn-gold btn-block" onClick={doSignup} disabled={busy} data-testid="signup-submit-btn">{busy ? "..." : "Criar conta"}</button>
        )}
        <p style={{ textAlign: "center", marginTop: ".7rem", fontSize: ".82rem" }}>
          <span className="link" onClick={() => setForgot(true)} data-testid="forgot-link">Esqueci minha senha</span>
        </p>
      </div>
    </div>
  );
}
function tabStyle(active) {
  return {
    flex: 1, padding: ".55rem", borderRadius: "100px",
    fontWeight: 700, fontSize: ".85rem",
    background: active ? "var(--gold)" : "transparent",
    color: active ? "#1a1205" : "var(--text-dim)",
    cursor: "pointer", border: "none",
  };
}

// ===== Verify code =====
function VerifyView({ email, devCode, onVerified, toast, onBack }) {
  const [code, setCode] = useState(devCode || "");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (code.length !== 6) { toast("Código de 6 dígitos"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/auth/verify", { email, code });
      onVerified(data.user);
    } catch (e) {
      toast(e.response?.data?.detail || "Erro");
    }
    setBusy(false);
  };
  const resend = async () => {
    try {
      const { data } = await api.post("/auth/resend-code", { email });
      if (data.dev_code) { setCode(data.dev_code); toast(`Código: ${data.dev_code}`); }
      else { toast("Código reenviado"); }
    }
    catch (e) { toast(e.response?.data?.detail || "Erro"); }
  };
  return (
    <div className="shell">
      <div className="card-auth">
        <h1 className="display">Confirma teu e-mail</h1>
        <p className="sub">Mandamos um código de 6 dígitos pra <b style={{ color: "var(--gold)" }}>{email}</b>. Procura na caixa de entrada (ou spam).</p>
        {devCode && (
          <div style={{ background: "rgba(255,194,61,.13)", border: "1px solid var(--gold)", borderRadius: "12px", padding: ".8rem 1rem", marginBottom: "1rem", fontSize: ".82rem", color: "var(--gold-hi)" }}>
            <b>📬 Modo dev:</b> e-mail não pôde ser enviado. Teu código é:
            <div style={{ fontFamily: "'Space Mono',monospace", fontSize: "1.4rem", letterSpacing: ".4em", color: "var(--gold)", textAlign: "center", margin: ".5rem 0", fontWeight: 700 }} data-testid="dev-code">{devCode}</div>
            <small style={{ color: "var(--text-dim)" }}>Já preenchemos pra ti — só clica Confirmar.</small>
          </div>
        )}
        <div className="field"><label>Código</label>
          <input type="text" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ""))} maxLength={6} className="code-input" style={{ textAlign: "center", fontFamily: "'Space Mono',monospace", fontSize: "1.5rem", letterSpacing: ".4em" }} placeholder="------" data-testid="verify-code-input" />
        </div>
        <button className="btn btn-gold btn-block" onClick={submit} disabled={busy} data-testid="verify-submit-btn">{busy ? "..." : "Confirmar"}</button>
        <p style={{ textAlign: "center", marginTop: ".8rem", fontSize: ".82rem" }}>
          <span className="link" onClick={resend} data-testid="resend-code-btn">Reenviar código</span> · <span className="link" onClick={onBack}>← Voltar</span>
        </p>
      </div>
    </div>
  );
}

// ===== Role pick =====
function RolePick({ onPick }) {
  const [sel, setSel] = useState("atleta");
  return (
    <div className="shell">
      <div className="card-auth">
        <h1 className="display">Salve! Bora começar?</h1>
        <p className="sub">Escolhe teu perfil. Dá pra mudar depois.</p>
        <div className="role-pick">
          <button className={`role-opt ${sel === "atleta" ? "sel" : ""}`} onClick={() => setSel("atleta")} data-testid="role-atleta">
            <b>Sou atleta</b><small>Busco oportunidades</small>
          </button>
          <button className={`role-opt ${sel === "tecnico" ? "sel" : ""}`} onClick={() => setSel("tecnico")} data-testid="role-tecnico">
            <b>Sou técnico</b><small>Busco jogadores</small>
          </button>
        </div>
        <button className="btn btn-gold btn-block" onClick={() => onPick(sel)} data-testid="confirm-role-btn">Continuar</button>
      </div>
    </div>
  );
}

// ===== Auth callback =====
function AuthCallback() {
  const navigate = useNavigate();
  const processed = React.useRef(false);
  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const hash = window.location.hash || "";
    const m = hash.match(/session_id=([^&]+)/);
    if (!m) { navigate("/", { replace: true }); return; }
    const session_id = m[1];
    (async () => {
      try {
        const { data } = await api.post("/auth/session", { session_id });
        window.history.replaceState(null, "", "/dashboard");
        navigate("/dashboard", { replace: true, state: { user: data.user } });
      } catch {
        navigate("/", { replace: true });
      }
    })();
  }, [navigate]);
  return <div className="shell"><div className="card-auth"><h1 className="display">Entrando…</h1></div></div>;
}

// ===== Athlete dashboard =====
function AthleteView({ user, toast, onOpenCv }) {
  const [p, setP] = useState(null);
  const [vTitle, setVTitle] = useState("");
  const [vUrl, setVUrl] = useState("");
  const [evo, setEvo] = useState([]);
  const [views, setViews] = useState([]);
  const [aiText, setAiText] = useState("");
  const [aiLoad, setAiLoad] = useState(false);

  const load = useCallback(async () => {
    const { data } = await api.get("/athlete/me");
    setP({
      name: data.name || user.name, age: data.age || "", city: data.city || "",
      sport: data.sport || "Futebol", position: data.position || "",
      height: data.height || "", weight: data.weight || "", dominant: data.dominant || "Destro",
      history: data.history || "", bio: data.bio || "", photo: data.photo || user.picture || "",
      videos: data.videos || [], attrs: data.attrs || emptyAttrs(), verified: !!data.verified,
      scores: data.scores,
    });
    const [e, v] = await Promise.all([api.get("/athlete/evolution"), api.get("/athlete/views")]);
    setEvo(e.data); setViews(v.data);
  }, [user]);

  // eslint-disable-next-line
  useEffect(() => { load(); }, [load]);

  if (!p) return <div className="app"><div className="panel">Carregando…</div></div>;

  const scores = p.scores || { fisico: 70, tecnico: 70, mental: 70, overall: 70 };
  const completion = (() => {
    const fields = [p.age, p.city, p.position, p.height, p.weight, p.bio, p.history, p.photo, p.videos.length > 0];
    return Math.round(fields.filter(Boolean).length / fields.length * 100);
  })();

  const update = (k, v) => setP({ ...p, [k]: v });
  const updateAttr = (k, v) => setP({ ...p, attrs: { ...p.attrs, [k]: Number(v) } });

  const addVideo = () => {
    if (!vUrl.trim() || !embedUrl(vUrl)) { toast("URL inválida (YouTube ou Drive)"); return; }
    const newV = { id: "v" + Date.now(), title: vTitle || "Lance", url: vUrl, pinned: p.videos.length === 0 };
    setP({ ...p, videos: [...p.videos, newV] });
    setVTitle(""); setVUrl("");
  };

  const uploadVideoFile = async (file) => {
    if (!file) return;
    if (file.size > 100_000_000) { toast("Vídeo muito grande (máx 100MB)"); return; }
    toast("Enviando vídeo… aguarda");
    try {
      const { data: sig } = await api.post("/upload/sign");
      const fd = new FormData();
      fd.append("file", file);
      fd.append("api_key", sig.api_key);
      fd.append("timestamp", sig.timestamp);
      fd.append("folder", sig.folder);
      fd.append("signature", sig.signature);
      const res = await fetch(`https://api.cloudinary.com/v1_1/${sig.cloud_name}/auto/upload`, { method: "POST", body: fd });
      const out = await res.json();
      if (!out.secure_url) throw new Error(out.error?.message || "Falha no upload");
      const newV = { id: "v" + Date.now(), title: vTitle || file.name, url: out.secure_url, pinned: p.videos.length === 0, cloudinary: true };
      setP({ ...p, videos: [...p.videos, newV] });
      setVTitle("");
      toast("Vídeo enviado! 🎥");
    } catch (e) {
      toast("Erro no upload do vídeo");
    }
  };
  const pinVideo = (id) => setP({ ...p, videos: p.videos.map(x => ({ ...x, pinned: x.id === id })) });
  const delVideo = (id) => setP({ ...p, videos: p.videos.filter(x => x.id !== id) });

  const save = async () => {
    const clean = { ...p };
    ["age", "height", "weight"].forEach(k => {
      if (clean[k] === "" || clean[k] === null || clean[k] === undefined) delete clean[k];
      else clean[k] = Number(clean[k]);
    });
    try {
      const { data } = await api.put("/athlete/me", clean);
      setP({ ...p, scores: data.scores, verified: data.verified });
      toast("Perfil salvo! ⚽");
      load();
    } catch (e) {
      toast("Erro ao salvar perfil");
    }
  };

  const onPhoto = (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    if (f.size > 2_000_000) { toast("Foto muito grande (máx 2MB)"); return; }
    const r = new FileReader();
    r.onload = () => update("photo", r.result);
    r.readAsDataURL(f);
  };

  const runAI = async () => {
    setAiLoad(true); setAiText("");
    try {
      const { data } = await api.post("/ai/analyze", { focus: p.position || "evoluir no esporte" });
      setAiText(data.analysis);
    } catch { toast("Erro na IA"); }
    setAiLoad(false);
  };

  const pinnedVid = p.videos.find(v => v.pinned) || p.videos[0];
  const pinnedEmbed = pinnedVid ? embedUrl(pinnedVid.url) : null;
  return (
    <div className="app">
      <div className="dash-head">
        <span className="ey">Painel do atleta</span>
        <h1 className="display">Salve, {user.name?.split(" ")[0]}!</h1>
        <p>Monta teu currículo esportivo, adiciona vídeos e mede teus atributos. Quanto mais completo, mais fácil de ser achado.</p>
      </div>

      <div className="completer">
        <div className="comp-top"><span>Perfil {completion}% completo</span><span className="comp-pct">{completion}%</span></div>
        <div className="comp-bar"><i style={{ width: `${completion}%` }}></i></div>
      </div>

      <div className="panel">
        <div className="panel-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg>
          Meu perfil
        </div>
        <div className="split">
          <div>
            <div className="photo-row">
              <div className="avatar">{p.photo ? <img src={p.photo} alt={p.name} /> : initials(p.name)}</div>
              <div>
                <label className="btn btn-ghost btn-sm" data-testid="photo-upload-btn">
                  Trocar foto
                  <input type="file" accept="image/*" onChange={onPhoto} hidden />
                </label>
                <p className="field-hint">Foto de rosto, quadrada de preferência. Máx 2MB.</p>
              </div>
            </div>

            <div className="field-row">
              <div className="field"><label>Idade</label><input type="number" value={p.age} onChange={e => update("age", e.target.value ? Number(e.target.value) : "")} data-testid="age-input" placeholder="16" /></div>
              <div className="field"><label>Cidade</label><input type="text" value={p.city} onChange={e => update("city", e.target.value)} data-testid="city-input" placeholder="Rio de Janeiro" /></div>
            </div>
            <div className="field-row">
              <div className="field"><label>Esporte</label>
                <select value={p.sport} onChange={e => update("sport", e.target.value)} data-testid="sport-select">
                  {SPORTS.map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
              <div className="field"><label>Posição / prova</label><input type="text" value={p.position} onChange={e => update("position", e.target.value)} data-testid="position-input" placeholder="Ala, zagueiro..." /></div>
            </div>
            <div className="field-row-3">
              <div className="field"><label>Altura (cm)</label><input type="number" value={p.height} onChange={e => update("height", e.target.value ? Number(e.target.value) : "")} data-testid="height-input" placeholder="175" /></div>
              <div className="field"><label>Peso (kg)</label><input type="number" value={p.weight} onChange={e => update("weight", e.target.value ? Number(e.target.value) : "")} data-testid="weight-input" placeholder="68" /></div>
              <div className="field"><label>Pé / mão</label>
                <select value={p.dominant} onChange={e => update("dominant", e.target.value)}>
                  <option>Destro</option><option>Canhoto</option><option>Ambidestro</option>
                </select>
              </div>
            </div>
            <div className="field"><label>Histórico</label><textarea value={p.history} onChange={e => update("history", e.target.value)} placeholder="Ex: Club Municipal (2023–24), peneira Flamengo sub-15..." data-testid="history-input" /></div>
            <div className="field"><label>Sobre / conquistas</label><textarea value={p.bio} onChange={e => update("bio", e.target.value)} placeholder="Ex: Artilheiro 2024, canhoto, rápido." data-testid="bio-input" /></div>

            <div className="panel-title" style={{ fontSize: ".98rem", margin: "1.3rem 0 .7rem" }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
              Vídeos de lances
            </div>
            <div className="field-row" style={{ gridTemplateColumns: "1fr .8fr", alignItems: "end" }}>
              <div className="field" style={{ margin: 0 }}><label>Título</label><input type="text" value={vTitle} onChange={e => setVTitle(e.target.value)} placeholder="Gol de cobertura" data-testid="video-title-input" /></div>
              <button className="btn btn-gold btn-sm" onClick={addVideo} data-testid="add-video-btn" style={{ height: "fit-content" }}>+ Adicionar</button>
            </div>
            <div className="field" style={{ marginTop: ".7rem" }}><label>Link (YouTube ou Drive)</label><input type="url" value={vUrl} onChange={e => setVUrl(e.target.value)} placeholder="https://youtube.com/watch?v=..." data-testid="video-url-input" /></div>
            <div style={{ display: "flex", alignItems: "center", gap: ".7rem", margin: ".4rem 0 .7rem", color: "var(--text-faint)", fontSize: ".75rem" }}>
              <div style={{ flex: 1, height: 1, background: "var(--line)" }}></div>OU FAÇA UPLOAD<div style={{ flex: 1, height: 1, background: "var(--line)" }}></div>
            </div>
            <label className="btn btn-azure btn-block" data-testid="video-upload-btn" style={{ cursor: "pointer" }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
              📹 Enviar vídeo (até 100MB)
              <input type="file" accept="video/*" hidden onChange={e => uploadVideoFile(e.target.files?.[0])} />
            </label>
            <div className="vid-list">
              {p.videos.map(v => (
                <div className="vid-item" key={v.id}>
                  <div className="vi-main"><b>{v.title}</b><small>{v.url}</small></div>
                  <button className={`star ${v.pinned ? "on" : ""}`} onClick={() => pinVideo(v.id)} title="Fixar">★</button>
                  <button className="del" onClick={() => delVideo(v.id)} title="Excluir">✕</button>
                </div>
              ))}
            </div>

            <div className="panel-title" style={{ fontSize: ".98rem", margin: "1.3rem 0 .7rem" }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 17l6-6 4 4 8-8"/></svg>
              Meus atributos
            </div>
            <div className="info-banner">
              <span><b>De onde vêm os números?</b> Cada atributo tem um teste — toca no <b>?</b>. Você se autoavalia; quando um técnico vê teu vídeo, ele confirma e vira <b>✓ Verificado</b>.</span>
            </div>
            {ATTR_CATS.map(cat => (
              <div className="cat-group" key={cat.name}>
                <div className="cat-name">{cat.name}</div>
                {cat.attrs.map(a => <AttrSlider key={a.k} a={a} value={p.attrs[a.k]} onChange={v => updateAttr(a.k, v)} />)}
              </div>
            ))}

            <div style={{ display: "flex", gap: ".7rem", flexWrap: "wrap", marginTop: "1.2rem" }}>
              <button className="btn btn-gold" onClick={save} data-testid="save-profile-btn">Salvar perfil</button>
              <button className="btn btn-ghost" onClick={() => onOpenCv(user.user_id)} data-testid="view-cv-btn">Ver meu currículo</button>
              <button className="btn btn-azure" onClick={runAI} data-testid="ai-analyze-btn" disabled={aiLoad}>{aiLoad ? "Analisando…" : "🧠 Análise da IA"}</button>
            </div>
            {aiText && <div className="ai-box" data-testid="ai-result">{aiText}</div>}
          </div>

          <div className="pcard">
            <div className="pcard-top"><span className="pcard-logo"><span className="dot"></span>FUT CONNECT</span></div>
            <div className="pcard-hero">
              <div className="avatar">{p.photo ? <img src={p.photo} alt={p.name}/> : initials(p.name)}</div>
              <div><div className="nm">{p.name || "Teu nome"}</div><div className="meta">{(p.position || "POSIÇÃO")} · {(p.city || "CIDADE")}</div></div>
            </div>
            <div className="vid">
              {pinnedEmbed
                ? (pinnedEmbed.type === "video"
                    ? <video src={pinnedEmbed.src} controls style={{ width: "100%", height: "100%", objectFit: "cover", position: "absolute", inset: 0 }} />
                    : <iframe src={pinnedEmbed.src} title="lance" allowFullScreen></iframe>)
                : <div className="hint">Adiciona um vídeo pra ele aparecer aqui 🎥</div>}
              <span className="ovr"><b>{scores.overall}</b><small>GERAL</small></span>
            </div>
            <div className="stat-row">
              <div className="stat"><b>{scores.fisico}</b><small>Físico</small></div>
              <div className="stat"><b>{scores.tecnico}</b><small>Técnico</small></div>
              <div className="stat"><b>{scores.mental}</b><small>Mental</small></div>
            </div>
            <div className="level">
              <div className="lvl-top"><span>Geral <b>{scores.overall}</b> — <b>{rankFor(scores.overall)}</b></span><span>{scores.overall} / 99</span></div>
              <div className="bar"><i style={{ width: `${scores.overall}%` }}></i></div>
            </div>
            <div className="chips">
              <span className={`chip ${p.verified ? "ok" : "auto"}`}>{p.verified ? "✓ Verificado por técnico" : "⏳ Auto-avaliação"}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 3v18h18M7 14l4-4 3 3 5-6"/></svg> Minha evolução</div>
        {evo.length === 0 ? <p style={{ color: "var(--text-dim)", fontSize: ".9rem" }}>Salva teu perfil pra criar o histórico.</p> :
          <div style={{ display: "flex", gap: ".4rem", overflowX: "auto", padding: ".3rem 0" }}>
            {evo.slice(-14).map((e, i) => (
              <div key={i} style={{ minWidth: "60px", textAlign: "center", background: "var(--bg-2)", border: "1px solid var(--line)", borderRadius: "10px", padding: ".5rem" }}>
                <div style={{ fontFamily: "Anton", color: "var(--gold)", fontSize: "1.1rem" }}>{e.overall}</div>
                <div className="mono" style={{ fontSize: ".58rem", color: "var(--text-dim)" }}>{e.date.slice(5)}</div>
              </div>
            ))}
          </div>
        }
      </div>

      <div className="panel">
        <div className="panel-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg> Quem viu meu perfil</div>
        <div className="rowlist">
          {views.length === 0 ? <p style={{ color: "var(--text-dim)", fontSize: ".9rem" }}>Ainda ninguém viu — compartilha teu currículo!</p> :
            views.slice(0, 10).map((v, i) => (
              <div className="rowitem" key={i}>
                <div className="av">{initials(v.viewer_name)}</div>
                <div className="main"><b>{v.viewer_name || "Técnico"}</b><small>{new Date(v.ts * 1000).toLocaleDateString("pt-BR")}</small></div>
              </div>
            ))
          }
        </div>
      </div>
    </div>
  );
}

function AttrSlider({ a, value, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="attr">
      <div className="attr-top">
        <span className="lab">{a.label} <button className="qmark" onClick={() => setOpen(!open)} title={a.tip}>?</button></span>
        <b>{value}</b>
      </div>
      <input type="range" min="0" max="99" value={value} onChange={e => onChange(e.target.value)} data-testid={`attr-${a.k}`} />
      {open && <p className="attr-hint">{a.tip}</p>}
    </div>
  );
}

// ===== Coach dashboard =====
function CoachView({ user, toast, onOpenCv }) {
  const [coach, setCoach] = useState({ club: "", city: "", sport: "Futebol", category: "" });
  const [q, setQ] = useState({ sport: "Futebol", position: "", city: "", max_age: 25, min_height: 150, only_verified: false, min_overall: 70, min_fisico: 60, min_tecnico: 60, min_mental: 60 });
  const [results, setResults] = useState([]);
  const [searched, setSearched] = useState(false);
  const [highlights, setHighlights] = useState([]);
  const [favs, setFavs] = useState([]);
  const [aiText, setAiText] = useState("");
  const [aiLoad, setAiLoad] = useState(false);

  const loadCoach = useCallback(async () => {
    const { data } = await api.get("/coach/me");
    if (data && data.club) setCoach({ club: data.club || "", city: data.city || "", sport: data.sport || "Futebol", category: data.category || "" });
  }, []);
  const loadHighlights = useCallback(async (sport) => {
    const { data } = await api.get(`/athletes/highlights/${encodeURIComponent(sport)}`);
    setHighlights(data);
  }, []);
  const loadFavs = useCallback(async () => {
    const { data } = await api.get("/favorites"); setFavs(data);
  }, []);

  // eslint-disable-next-line
  useEffect(() => { loadCoach(); loadFavs(); loadHighlights(q.sport); }, [loadCoach, loadFavs, loadHighlights, q.sport]);

  const saveCoach = async () => { await api.put("/coach/me", coach); toast("Clube salvo! 🏆"); };

  const search = async () => {
    const payload = {
      sport: q.sport,
      position: q.position || null,
      city: q.city || null,
      max_age: q.max_age || null,
      min_height: q.min_height || null,
      only_verified: q.only_verified,
      min_overall: q.min_overall, min_fisico: q.min_fisico, min_tecnico: q.min_tecnico, min_mental: q.min_mental,
    };
    const { data } = await api.post("/athletes/search", payload);
    setResults(data); setSearched(true);
  };

  const runAI = async () => {
    setAiLoad(true); setAiText("");
    try {
      const { data } = await api.post("/ai/recommend", { sport: q.sport, position: q.position, notes: coach.category });
      setAiText(data.recommendation);
    } catch { toast("Erro na IA"); }
    setAiLoad(false);
  };

  const toggleFav = async (athId) => {
    await api.post("/favorites/toggle", { athlete_user_id: athId });
    loadFavs();
  };

  return (
    <div className="app">
      <div className="dash-head">
        <span className="ey">Painel do técnico</span>
        <h1 className="display">Salve, treinador!</h1>
        <p>Cadastra teu clube, busca atletas, vê o currículo, favorita e chama. A IA te indica quem mais combina.</p>
      </div>

      <div className="panel">
        <div className="panel-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2l2.4 7.4H22l-6 4.4 2.3 7.2-6.3-4.6L5.7 21l2.3-7.2-6-4.4h7.6z"/></svg> Destaques · ranking por esporte</div>
        <div className="field" style={{ maxWidth: "320px", marginBottom: "1rem" }}>
          <label>Esporte do ranking</label>
          <select value={q.sport} onChange={e => setQ({ ...q, sport: e.target.value })} data-testid="highlight-sport-select">
            {SPORTS.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="rowlist">
          {highlights.length === 0 ? <p style={{ color: "var(--text-dim)", fontSize: ".9rem" }}>Sem atletas neste esporte ainda.</p> :
            highlights.map((a, i) => (
              <div className="rowitem" key={a.user_id}>
                <div className="av">{a.photo ? <img src={a.photo} alt={a.name} /> : initials(a.name)}</div>
                <div className="main"><b>#{i + 1} {a.name}</b><small>{a.position} · {a.city}</small></div>
                <div className="score">{a.scores.overall}</div>
                <button className="btn btn-ghost btn-sm" onClick={() => onOpenCv(a.user_id)} data-testid={`view-athlete-${a.user_id}`}>Ver</button>
              </div>
            ))
          }
        </div>
      </div>

      <div className="panel">
        <div className="panel-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 21h18M5 21V7l8-4 8 4v14"/></svg> Meu clube / escola</div>
        <div className="search-grid">
          <div className="field"><label>Nome do clube</label><input value={coach.club} onChange={e => setCoach({ ...coach, club: e.target.value })} placeholder="Base Rio FC" data-testid="club-name-input" /></div>
          <div className="field"><label>Cidade</label><input value={coach.city} onChange={e => setCoach({ ...coach, city: e.target.value })} placeholder="Rio de Janeiro" /></div>
          <div className="field"><label>Esporte</label><select value={coach.sport} onChange={e => setCoach({ ...coach, sport: e.target.value })}>{SPORTS.map(s => <option key={s}>{s}</option>)}</select></div>
          <div className="field"><label>Categoria</label><input value={coach.category} onChange={e => setCoach({ ...coach, category: e.target.value })} placeholder="Sub-15, base, profissional" /></div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={saveCoach} data-testid="save-club-btn">Salvar clube</button>
      </div>

      <div className="panel">
        <div className="panel-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg> Buscar atletas</div>
        <div className="search-grid">
          <div className="field"><label>Esporte</label><select value={q.sport} onChange={e => setQ({ ...q, sport: e.target.value })}>{SPORTS.map(s => <option key={s}>{s}</option>)}</select></div>
          <div className="field"><label>Posição</label><input value={q.position} onChange={e => setQ({ ...q, position: e.target.value })} placeholder="Ala..." /></div>
          <div className="field"><label>Cidade</label><input value={q.city} onChange={e => setQ({ ...q, city: e.target.value })} placeholder="Rio..." /></div>
          <div className="field"><label>Idade máx</label><input type="number" value={q.max_age} onChange={e => setQ({ ...q, max_age: Number(e.target.value) })} /></div>
          <div className="field"><label>Altura mín (cm)</label><input type="number" value={q.min_height} onChange={e => setQ({ ...q, min_height: Number(e.target.value) })} /></div>
          <div className="field" style={{ display: "flex", alignItems: "end" }}>
            <label style={{ display: "flex", alignItems: "center", gap: ".5rem", letterSpacing: 0, textTransform: "none", color: "var(--text)", fontFamily: "inherit", fontSize: ".86rem" }}>
              <input type="checkbox" checked={q.only_verified} onChange={e => setQ({ ...q, only_verified: e.target.checked })} style={{ width: "auto" }} /> Só verificados
            </label>
          </div>
        </div>
        <div className="field" style={{ marginTop: ".3rem" }}><label>Mínimos</label>
          <div className="mins-grid">
            {[["min_overall", "Geral"], ["min_fisico", "Físico"], ["min_tecnico", "Técnico"], ["min_mental", "Mental"]].map(([k, lab]) => (
              <div className="attr" key={k}>
                <div className="attr-top"><span className="lab">{lab}</span><b>{q[k]}</b></div>
                <input type="range" min="0" max="99" value={q[k]} onChange={e => setQ({ ...q, [k]: Number(e.target.value) })} />
              </div>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", gap: ".7rem", marginTop: "1rem", flexWrap: "wrap" }}>
          <button className="btn btn-gold" onClick={search} data-testid="search-btn">Buscar</button>
          <button className="btn btn-azure" onClick={runAI} disabled={aiLoad} data-testid="ai-recommend-btn">{aiLoad ? "IA pensando…" : "🧠 IA — Top 3 indicados"}</button>
        </div>
        {aiText && <div className="ai-box" data-testid="ai-rec-result">{aiText}</div>}
      </div>

      <div className="results-head"><h2>Resultados</h2><span className="count">{searched ? `${results.length} atletas` : "Faça uma busca pra ver os talentos."}</span></div>
      <div className="results" data-testid="search-results">
        {results.map(a => (
          <div className="acard" key={a.user_id} onClick={() => onOpenCv(a.user_id)} data-testid={`athlete-card-${a.user_id}`}>
            <div className="ah">
              <div className="avatar" style={{ width: 44, height: 44, fontSize: "1rem" }}>{a.photo ? <img src={a.photo} alt={a.name} /> : initials(a.name)}</div>
              <div><div className="nm">{a.name}</div><div className="meta">{a.position || "—"} · {a.city || "—"}</div></div>
              <div className="av-num">{a.scores.overall}</div>
            </div>
            <div className="as">
              <div><b>{a.scores.fisico}</b><small>FÍS</small></div>
              <div><b>{a.scores.tecnico}</b><small>TÉC</small></div>
              <div><b>{a.scores.mental}</b><small>MEN</small></div>
            </div>
          </div>
        ))}
      </div>

      <div className="panel" style={{ marginTop: "1.3rem" }}>
        <div className="panel-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 21s-7-4.4-7-10a4 4 0 017-2.6A4 4 0 0119 11c0 5.6-7 10-7 10z"/></svg> Meus favoritos</div>
        <div className="rowlist">
          {favs.length === 0 ? <p style={{ color: "var(--text-dim)", fontSize: ".9rem" }}>Toque no ♥ num atleta pra favoritar.</p> :
            favs.map(a => (
              <div className="rowitem" key={a.user_id}>
                <div className="av">{a.photo ? <img src={a.photo} alt={a.name} /> : initials(a.name)}</div>
                <div className="main"><b>{a.name}</b><small>{a.position} · {a.city}</small></div>
                <div className="score">{a.scores.overall}</div>
                <button className="btn btn-ghost btn-sm" onClick={() => toggleFav(a.user_id)}>Remover</button>
                <button className="btn btn-ghost btn-sm" onClick={() => onOpenCv(a.user_id)}>Ver</button>
              </div>
            ))
          }
        </div>
      </div>
    </div>
  );
}

// ===== Chat =====
function ChatView({ user, toast, initialOtherId, onBack }) {
  const [convos, setConvos] = useState([]);
  const [openId, setOpenId] = useState(initialOtherId || null);
  const [thread, setThread] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = React.useRef(null);

  const loadConvos = useCallback(async () => {
    try {
      const { data } = await api.get("/conversations");
      setConvos(data);
    } catch (e) { /* ignore */ }
  }, []);

  const loadThread = useCallback(async (otherId) => {
    if (!otherId) return;
    try {
      const { data } = await api.get(`/messages/thread/${otherId}`);
      setThread(data);
      setTimeout(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); }, 60);
    } catch (e) { /* ignore */ }
  }, []);

  // eslint-disable-next-line
  useEffect(() => { loadConvos(); }, [loadConvos]);
  // eslint-disable-next-line
  useEffect(() => { if (openId) loadThread(openId); else setThread(null); }, [openId, loadThread]);

  // poll every 6s for live updates
  /* eslint-disable */
  useEffect(() => {
    const t = setInterval(() => {
      loadConvos();
      if (openId) loadThread(openId);
    }, 6000);
    return () => clearInterval(t);
  }, [openId, loadConvos, loadThread]);
  /* eslint-enable */

  const send = async () => {
    if (!text.trim() || !openId) return;
    setBusy(true);
    try {
      await api.post("/messages", { to_user_id: openId, text: text.trim() });
      setText("");
      await loadThread(openId);
      loadConvos();
    } catch { toast("Erro ao enviar"); }
    setBusy(false);
  };

  const fmt = (iso) => {
    try { const d = new Date(iso); return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) + " · " + d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }); } catch { return ""; }
  };

  return (
    <div className="app">
      <button className="btn btn-ghost btn-sm" onClick={onBack} style={{ marginBottom: "1rem" }} data-testid="chat-back-btn">← Voltar pro painel</button>
      <div className="dash-head">
        <span className="ey">Mensagens</span>
        <h1 className="display">Chat</h1>
        <p>Converse direto com atletas e técnicos. As novas mensagens aparecem em tempo real.</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 320px) 1fr", gap: "1rem", minHeight: "60vh" }} className="chat-layout">
        {/* Conversation list */}
        <div className="panel" style={{ padding: ".4rem", margin: 0, alignSelf: "start" }} data-testid="convo-list">
          {convos.length === 0 ? (
            <p style={{ color: "var(--text-dim)", fontSize: ".9rem", padding: "1rem" }}>Sem conversas ainda. Vá no currículo de alguém e mande mensagem.</p>
          ) : convos.map(c => (
            <button
              key={c.other_user_id}
              onClick={() => setOpenId(c.other_user_id)}
              data-testid={`convo-${c.other_user_id}`}
              style={{
                display: "flex", alignItems: "center", gap: ".7rem", width: "100%",
                padding: ".8rem", borderRadius: "12px", marginBottom: ".25rem",
                background: openId === c.other_user_id ? "var(--gold-soft)" : "transparent",
                border: "1px solid " + (openId === c.other_user_id ? "var(--gold)" : "transparent"),
                cursor: "pointer", textAlign: "left",
              }}
            >
              <div className="avatar" style={{ width: 40, height: 40, fontSize: ".95rem", flex: "none" }}>
                {c.other_photo ? <img src={c.other_photo} alt="" /> : initials(c.other_name)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: ".4rem" }}>
                  <b style={{ fontSize: ".9rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.other_name}</b>
                  {c.unread > 0 && <span style={{ background: "var(--gold)", color: "#1a1205", borderRadius: "100px", fontSize: ".62rem", fontWeight: 800, padding: "2px 7px" }}>{c.unread}</span>}
                </div>
                <small style={{ color: "var(--text-dim)", fontSize: ".75rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "block" }}>
                  {c.last_from_me ? "Você: " : ""}{c.last_text}
                </small>
              </div>
            </button>
          ))}
        </div>

        {/* Thread */}
        <div className="panel" style={{ display: "flex", flexDirection: "column", margin: 0, padding: 0, minHeight: "60vh" }}>
          {!openId ? (
            <div style={{ display: "grid", placeItems: "center", flex: 1, color: "var(--text-faint)", padding: "2rem" }}>
              Escolha uma conversa à esquerda. 💬
            </div>
          ) : !thread ? (
            <div style={{ padding: "1rem", color: "var(--text-dim)" }}>Carregando…</div>
          ) : (
            <>
              {/* header */}
              <div style={{ display: "flex", alignItems: "center", gap: ".7rem", padding: ".9rem 1.1rem", borderBottom: "1px solid var(--line)" }}>
                <div className="avatar" style={{ width: 42, height: 42, fontSize: "1rem", flex: "none" }}>
                  {thread.other?.picture ? <img src={thread.other.picture} alt="" /> : initials(thread.other?.name)}
                </div>
                <div style={{ flex: 1 }}>
                  <b data-testid="thread-other-name">{thread.other?.name}</b>
                  <div className="mono" style={{ color: "var(--text-dim)", fontSize: ".66rem", textTransform: "uppercase", letterSpacing: ".1em" }}>{thread.other?.role || "—"}</div>
                </div>
              </div>

              {/* messages */}
              <div ref={scrollRef} data-testid="thread-messages" style={{ flex: 1, overflowY: "auto", padding: "1rem", display: "flex", flexDirection: "column", gap: ".5rem", maxHeight: "55vh" }}>
                {thread.messages.length === 0
                  ? <p style={{ color: "var(--text-faint)", textAlign: "center", marginTop: "2rem" }}>Manda a primeira mensagem 👋</p>
                  : thread.messages.map(m => {
                      const mine = m.from_user_id === user.user_id;
                      return (
                        <div key={m.id} style={{ display: "flex", justifyContent: mine ? "flex-end" : "flex-start" }}>
                          <div style={{
                            maxWidth: "76%",
                            background: mine ? "var(--gold)" : "var(--bg-2)",
                            color: mine ? "#1a1205" : "var(--text)",
                            border: "1px solid " + (mine ? "var(--gold)" : "var(--line)"),
                            borderRadius: mine ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                            padding: ".6rem .85rem",
                            fontSize: ".92rem",
                            lineHeight: 1.4,
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                          }}>
                            {m.text}
                            <div style={{ marginTop: ".25rem", fontSize: ".6rem", opacity: .7, fontFamily: "'Space Mono',monospace" }}>{fmt(m.ts)}</div>
                          </div>
                        </div>
                      );
                  })
                }
              </div>

              {/* compose */}
              <div style={{ display: "flex", gap: ".5rem", padding: ".7rem .9rem", borderTop: "1px solid var(--line)" }}>
                <textarea
                  value={text}
                  onChange={e => setText(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                  placeholder="Escreva uma mensagem... (Enter envia)"
                  data-testid="chat-input"
                  style={{ flex: 1, background: "var(--bg-2)", border: "1px solid var(--line-strong)", borderRadius: "12px", padding: ".7rem .9rem", color: "var(--text)", fontFamily: "inherit", fontSize: ".95rem", resize: "none", minHeight: "44px", maxHeight: "120px" }}
                />
                <button className="btn btn-gold" onClick={send} disabled={busy || !text.trim()} data-testid="chat-send-btn">
                  Enviar
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ===== Public CV =====
function CvView({ athleteId, viewer, toast, onBack, onOpenChat }) {
  const [a, setA] = useState(null);
  const [msgOpen, setMsgOpen] = useState(false);
  const [msgText, setMsgText] = useState("");

  useEffect(() => { (async () => {
    try {
      const { data } = await api.get(`/athletes/${athleteId}`);
      setA(data);
    } catch (e) { toast("Atleta não encontrado"); onBack(); }
  })(); }, [athleteId, toast, onBack]);

  if (!a) return <div className="app"><div className="panel">Carregando…</div></div>;
  const sc = a.scores;
  const pinned = (a.videos || []).find(v => v.pinned) || (a.videos || [])[0];
  const pinnedEmbed = pinned ? embedUrl(pinned.url) : null;

  const verify = async () => { await api.post(`/athletes/${athleteId}/verify`); toast("Atleta verificado ✓"); setA({ ...a, verified: true }); };
  const sendMsg = async () => {
    if (!msgText.trim()) return;
    await api.post("/messages", { to_user_id: athleteId, text: msgText });
    toast("Mensagem enviada 📨"); setMsgOpen(false); setMsgText("");
  };
  const toggleFav = async () => { await api.post("/favorites/toggle", { athlete_user_id: athleteId }); toast("Favorito atualizado ♥"); };

  return (
    <div className="app">
      <button className="btn btn-ghost btn-sm" onClick={onBack} style={{ marginBottom: "1.2rem" }} data-testid="cv-back-btn">← Voltar</button>
      <div className="cv-head">
        <div className="avatar">{a.photo ? <img src={a.photo} alt={a.name}/> : initials(a.name)}</div>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", gap: ".4rem", marginBottom: ".5rem", flexWrap: "wrap" }}>
            <span className={`chip ${a.verified ? "ok" : "auto"}`}>{a.verified ? "✓ Verificado" : "⏳ Auto-avaliação"}</span>
            <span className="chip">{a.sport}</span>
          </div>
          <h1 className="display">{a.name}</h1>
          <div className="mono" style={{ color: "var(--text-dim)", fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>
            {(a.position || "—")} · {(a.city || "—")} · {a.age || "?"} anos
          </div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontFamily: "Anton", fontSize: "2.4rem", color: "var(--gold)", lineHeight: 1 }}>{sc.overall}</div>
          <div className="mono" style={{ fontSize: ".6rem", color: "var(--text-dim)", letterSpacing: ".1em" }}>GERAL</div>
        </div>
      </div>

      <div className="cv-grid">
        <div>
          <div className="vid" style={{ borderRadius: "var(--radius)", border: "1px solid var(--line-strong)" }}>
            {pinnedEmbed
              ? (pinnedEmbed.type === "video"
                  ? <video src={pinnedEmbed.src} controls style={{ width: "100%", height: "100%", objectFit: "cover", position: "absolute", inset: 0 }} />
                  : <iframe src={pinnedEmbed.src} title="lance" allowFullScreen></iframe>)
              : <div className="hint">Sem vídeo ainda</div>}
          </div>
          <div className="panel" style={{ marginTop: "1.2rem" }}>
            <div className="panel-title" style={{ fontSize: "1rem" }}>Estatísticas</div>
            <div className="stat-row" style={{ padding: 0, gridTemplateColumns: "repeat(3,1fr)" }}>
              <div className="stat"><b>{sc.fisico}</b><small>Físico</small></div>
              <div className="stat"><b>{sc.tecnico}</b><small>Técnico</small></div>
              <div className="stat"><b>{sc.mental}</b><small>Mental</small></div>
            </div>
            <div style={{ marginTop: ".8rem" }}>
              {ATTR_CATS.map(c => (
                <div key={c.name} className="cat-group" style={{ marginBottom: ".6rem" }}>
                  <div className="cat-name">{c.name}</div>
                  {c.attrs.map(at => (
                    <div className="attr" key={at.k}>
                      <div className="attr-top"><span className="lab">{at.label}</span><b>{a.attrs?.[at.k] ?? 0}</b></div>
                      <div className="bar"><i style={{ width: `${a.attrs?.[at.k] || 0}%` }}></i></div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
          {a.bio && <div className="panel"><div className="panel-title" style={{ fontSize: "1rem" }}>Sobre / conquistas</div><p style={{ color: "var(--text-dim)", fontSize: ".92rem" }}>{a.bio}</p></div>}
          {a.history && <div className="panel"><div className="panel-title" style={{ fontSize: "1rem" }}>Histórico</div><p style={{ color: "var(--text-dim)", fontSize: ".92rem" }}>{a.history}</p></div>}
        </div>
        <div>
          <div className="panel">
            <div className="panel-title" style={{ fontSize: "1rem" }}>Ficha</div>
            <div className="facts">
              <div><span>Esporte</span><span>{a.sport}</span></div>
              <div><span>Posição</span><span>{a.position || "—"}</span></div>
              <div><span>Idade</span><span>{a.age || "—"}</span></div>
              <div><span>Altura</span><span>{a.height ? a.height + " cm" : "—"}</span></div>
              <div><span>Peso</span><span>{a.weight ? a.weight + " kg" : "—"}</span></div>
              <div><span>Pé/mão</span><span>{a.dominant || "—"}</span></div>
              <div><span>Cidade</span><span>{a.city || "—"}</span></div>
            </div>
            {viewer && viewer.user_id !== athleteId && (
              <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: ".6rem" }}>
                <button className="btn btn-gold" onClick={() => onOpenChat && onOpenChat(athleteId)} data-testid="cv-message-btn">💬 Conversar</button>
                {viewer.role === "tecnico" && (
                  <>
                    <button className="btn btn-ghost" onClick={toggleFav} data-testid="cv-fav-btn">♥ Favoritar</button>
                    {!a.verified && <button className="btn btn-azure" onClick={verify} data-testid="cv-verify-btn">✓ Verificar</button>}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {msgOpen && (
        <div className="modal-bg" onClick={(e) => e.target === e.currentTarget && setMsgOpen(false)}>
          <div className="modal-card">
            <button className="close-x" onClick={() => setMsgOpen(false)}>✕</button>
            <h3 className="display" style={{ marginBottom: ".5rem" }}>Mensagem para {a.name}</h3>
            <div className="field"><textarea value={msgText} onChange={e => setMsgText(e.target.value)} placeholder="Olá, vi teu perfil..." data-testid="msg-text-input" /></div>
            <button className="btn btn-gold btn-block" onClick={sendMsg} data-testid="msg-send-btn">Enviar</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ===== Opportunities =====
function OppsView({ user, toast, onBack }) {
  const [opps, setOpps] = useState([]);
  const [filterSport, setFilterSport] = useState("");
  const [form, setForm] = useState({ title: "", sport: "Futebol", category: "", city: "", date: "", description: "" });
  const isCoach = user.role === "tecnico";

  const load = useCallback(async () => {
    const { data } = await api.get("/opportunities" + (filterSport ? `?sport=${encodeURIComponent(filterSport)}` : ""));
    setOpps(data);
  }, [filterSport]);
  // eslint-disable-next-line
  useEffect(() => { load(); }, [load]);

  const publish = async () => {
    if (!form.title.trim()) { toast("Coloca um título"); return; }
    await api.post("/opportunities", form);
    setForm({ title: "", sport: "Futebol", category: "", city: "", date: "", description: "" });
    toast("Oportunidade publicada ⚡"); load();
  };
  const del = async (id) => { await api.delete(`/opportunities/${id}`); load(); };
  const apply = async (id) => { await api.post("/opportunities/apply", { opp_id: id }); toast("Candidatura enviada 🚀"); };

  return (
    <div className="app">
      <button className="btn btn-ghost btn-sm" onClick={onBack} style={{ marginBottom: "1.2rem" }} data-testid="opps-back-btn">← Voltar pro painel</button>
      <div className="dash-head">
        <span className="ey">Mural de oportunidades</span>
        <h1 className="display">Peneiras & testes</h1>
        <p>Onde o talento encontra a chance.</p>
      </div>

      {isCoach && (
        <div className="panel">
          <div className="panel-title">+ Publicar oportunidade</div>
          <div className="search-grid">
            <div className="field"><label>Título</label><input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Peneira sub-15" data-testid="opp-title-input" /></div>
            <div className="field"><label>Esporte</label><select value={form.sport} onChange={e => setForm({ ...form, sport: e.target.value })}>{SPORTS.map(s => <option key={s}>{s}</option>)}</select></div>
            <div className="field"><label>Categoria</label><input value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} placeholder="Sub-15, base..." /></div>
            <div className="field"><label>Cidade</label><input value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} placeholder="Rio de Janeiro" /></div>
            <div className="field"><label>Data</label><input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} /></div>
          </div>
          <div className="field"><label>Descrição</label><textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="O que você procura, horário, o que levar..." /></div>
          <button className="btn btn-gold" onClick={publish} data-testid="opp-publish-btn">Publicar</button>
        </div>
      )}

      <div className="results-head">
        <h2>Oportunidades abertas</h2>
        <select value={filterSport} onChange={e => setFilterSport(e.target.value)} style={{ background: "var(--bg-2)", color: "var(--text)", border: "1px solid var(--line-strong)", borderRadius: "10px", padding: ".4rem .8rem" }}>
          <option value="">Todos esportes</option>
          {SPORTS.map(s => <option key={s}>{s}</option>)}
        </select>
      </div>
      <div className="rowlist" data-testid="opps-list">
        {opps.length === 0 ? <p style={{ color: "var(--text-dim)", fontSize: ".9rem" }}>Nada por aqui ainda.</p> :
          opps.map(o => (
            <div className="rowitem" key={o.id} style={{ flexWrap: "wrap" }}>
              <div className="main">
                <b>{o.title}</b>
                <small>{o.sport} · {o.category || "—"} · {o.city || "—"} · {o.date || "data a confirmar"}</small>
                {o.description && <p style={{ marginTop: ".3rem", fontSize: ".82rem", color: "var(--text-dim)" }}>{o.description}</p>}
                <small style={{ color: "var(--gold)" }}>Por {o.coach_name}</small>
              </div>
              {user.role === "atleta" && <button className="btn btn-gold btn-sm" onClick={() => apply(o.id)} data-testid={`apply-${o.id}`}>Candidatar</button>}
              {isCoach && o.coach_id === user.user_id && <button className="btn btn-ghost btn-sm" onClick={() => del(o.id)}>Excluir</button>}
            </div>
          ))
        }
      </div>
    </div>
  );
}

// ===== Dashboard wrapper =====
function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState(location.state?.user || null);
  const [loading, setLoading] = useState(!location.state?.user);
  const [page, setPage] = useState("home"); // home | cv | opps | chat
  const [cvId, setCvId] = useState(null);
  const [chatOpenId, setChatOpenId] = useState(null);
  const [unread, setUnread] = useState(0);
  const toast = React.useContext(ToastCtx);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (e) { navigate("/", { replace: true }); }
    setLoading(false);
  }, [navigate]);

  /* eslint-disable */
  useEffect(() => {
    if (user) { setLoading(false); return; }
    if (window.location.hash?.includes("session_id=")) return;
    checkAuth();
  }, [user, checkAuth]);
  /* eslint-enable */

  // Poll unread count
  /* eslint-disable */
  useEffect(() => {
    if (!user || !user.role) return;
    const refresh = async () => {
      try {
        const { data } = await api.get("/conversations");
        setUnread(data.reduce((s, c) => s + (c.unread || 0), 0));
      } catch (e) { /* ignore */ }
    };
    refresh();
    const t = setInterval(refresh, 12000);
    return () => clearInterval(t);
  }, [user, page]);
  /* eslint-enable */

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) { /* ignore */ }
    setUser(null); navigate("/", { replace: true });
  };
  const pickRole = async (r) => {
    await api.post("/auth/role", { role: r });
    setUser({ ...user, role: r });
  };
  const openCv = (id) => { setCvId(id); setPage("cv"); window.scrollTo(0, 0); };
  const openOpps = () => { setPage("opps"); window.scrollTo(0, 0); };
  const openChat = (otherId = null) => { setChatOpenId(otherId); setPage("chat"); window.scrollTo(0, 0); };
  const backHome = () => { setPage("home"); window.scrollTo(0, 0); };

  if (loading) return <div className="shell"><div className="card-auth"><h1 className="display">Carregando…</h1></div></div>;
  if (!user) return <Landing />;
  if (!user.role) return (<><Topbar user={user} onLogout={logout} onGoOpps={openOpps} onGoChat={() => openChat()} unread={unread} /><RolePick onPick={pickRole} /></>);

  return (
    <>
      <Topbar user={user} onLogout={logout} onGoOpps={openOpps} onGoChat={() => openChat()} unread={unread} />
      {page === "home" && user.role === "atleta" && <AthleteView user={user} toast={toast} onOpenCv={openCv} />}
      {page === "home" && user.role === "tecnico" && <CoachView user={user} toast={toast} onOpenCv={openCv} />}
      {page === "cv" && <CvView athleteId={cvId} viewer={user} toast={toast} onBack={backHome} onOpenChat={openChat} />}
      {page === "opps" && <OppsView user={user} toast={toast} onBack={backHome} />}
      {page === "chat" && <ChatView user={user} toast={toast} initialOtherId={chatOpenId} onBack={backHome} />}
    </>
  );
}

// ===== Landing (logged-out) =====
function Landing() {
  const navigate = useNavigate();
  const toast = React.useContext(ToastCtx);
  const [verifyState, setVerifyState] = useState(null); // { email, devCode }
  if (verifyState) {
    return (<><Topbar /><VerifyView email={verifyState.email} devCode={verifyState.devCode} toast={toast} onBack={() => setVerifyState(null)} onVerified={(u) => navigate("/dashboard", { state: { user: u } })} /></>);
  }
  return (<><Topbar /><LoginView toast={toast} onSignedIn={(u) => navigate("/dashboard", { state: { user: u } })} onNeedVerify={(em, code) => setVerifyState({ email: em, devCode: code })} /></>);
}

// ===== Router =====
function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="*" element={<Landing />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <ToastProvider>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </ToastProvider>
    </div>
  );
}

export default App;
