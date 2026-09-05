import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const api = axios.create({ baseURL: API, withCredentials: true });

function Stat({ label, value, unit, icon, goal }) {
  const pct = goal ? Math.max(0, Math.min(100, Math.round((Number(value) / goal) * 100))) : null;
  return (
    <div className="health-stat" data-testid={`health-stat-${label}`}>
      <div className="health-stat-icon">{icon}</div>
      <div style={{ flex: 1 }}>
        <div className="health-stat-value">{value}<span className="health-stat-unit">{unit}</span></div>
        <div className="health-stat-label">{label}</div>
        {pct !== null && (
          <div className="health-goal-bar" title={`${pct}% da meta (${goal}${unit})`}>
            <i style={{ width: `${pct}%` }} />
          </div>
        )}
      </div>
    </div>
  );
}

function LineChart({ points, color = "var(--gold)", width = 280, height = 70, formatValue }) {
  const vals = points.map((p) => p.value ?? 0);
  const max = Math.max(...vals, 1);
  const min = Math.min(...vals, 0);
  const range = max - min || 1;
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  const coords = points.map((p, i) => {
    const x = i * stepX;
    const y = height - ((p.value ?? 0) - min) / range * (height - 10) - 5;
    return { x, y, ...p };
  });
  const path = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="health-chart-svg" preserveAspectRatio="none">
      <path d={path} fill="none" stroke={color} strokeWidth="2" />
      {coords.map((c, i) => (
        <circle key={i} cx={c.x} cy={c.y} r="2.5" fill={color}>
          <title>{`${c.date}: ${formatValue ? formatValue(c.value) : c.value}`}</title>
        </circle>
      ))}
    </svg>
  );
}

function ChartCard({ title, points, unit }) {
  const hasData = points.some((p) => p.value !== null && p.value !== undefined && p.value !== 0);
  return (
    <div className="health-card" data-testid={`chart-${title}`}>
      <h3>{title}</h3>
      {hasData ? (
        <LineChart points={points} formatValue={(v) => `${v}${unit || ""}`} />
      ) : (
        <div className="health-chart-empty">Sem dados ainda</div>
      )}
    </div>
  );
}

function QuickForm({ testId, placeholder, buttonLabel, onSubmit, type = "number", step = "1" }) {
  const [val, setVal] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (val === "" || Number(val) < 0) return;
    setBusy(true);
    try {
      await onSubmit(Number(val));
      setVal("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="health-quickform" onSubmit={submit} data-testid={testId}>
      <input
        type={type}
        step={step}
        min="0"
        placeholder={placeholder}
        value={val}
        onChange={(e) => setVal(e.target.value)}
        className="health-input"
      />
      <button className="btn btn-primary btn-sm" type="submit" disabled={busy}>{buttonLabel}</button>
    </form>
  );
}

export default function HealthView({ toast }) {
  const [today, setToday] = useState(null);
  const [history, setHistory] = useState([]);
  const [weightHistory, setWeightHistory] = useState([]);
  const [sleepHistory, setSleepHistory] = useState([]);
  const [fitbit, setFitbit] = useState({ configured: false, connected: false });
  const [fitbitBusy, setFitbitBusy] = useState(false);
  const [strava, setStrava] = useState({ configured: false, connected: false });
  const [stravaBusy, setStravaBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [t, h, w, sl, f, s] = await Promise.all([
        api.get("/health/today"),
        api.get("/health/history?days=7"),
        api.get("/health/weight/history?days=30"),
        api.get("/health/sleep/history?days=14"),
        api.get("/health/fitbit/status"),
        api.get("/health/strava/status"),
      ]);
      setToday(t.data);
      setHistory(h.data.days);
      setWeightHistory(w.data.entries);
      setSleepHistory(sl.data.entries);
      setFitbit(f.data);
      setStrava(s.data);
    } catch (e) {
      toast?.("Erro ao carregar dados de saúde");
    }
    setLoading(false);
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fitbitStatus = params.get("fitbit");
    const stravaStatus = params.get("strava");
    if (!fitbitStatus && !stravaStatus) return;
    if (fitbitStatus === "connected") toast?.("Fitbit conectado! 🎉");
    if (fitbitStatus === "error") toast?.("Não foi possível conectar ao Fitbit");
    if (stravaStatus === "connected") toast?.("Strava conectado! 🎉");
    if (stravaStatus === "error") toast?.("Não foi possível conectar ao Strava");
    params.delete("fitbit");
    params.delete("strava");
    const q = params.toString();
    window.history.replaceState({}, "", window.location.pathname + (q ? `?${q}` : ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ok = (msg) => toast?.(msg);

  const addWater = async (liters) => { await api.post("/health/water", { liters }); ok("Água registrada 💧"); load(); };
  const addBpm = async (bpm) => { await api.post("/health/bpm", { bpm, source: "manual" }); ok("BPM registrado ❤️"); load(); };
  const addActivity = async (km) => { await api.post("/health/activity", { km, source: "manual" }); ok("Caminhada registrada 🚶"); load(); };
  const addBurned = async (kcal) => { await api.post("/health/burned", { kcal, source: "manual" }); ok("Kcal perdida registrada 🔥"); load(); };
  const addWeight = async (kg) => { await api.post("/health/weight", { kg }); ok("Peso registrado ⚖️"); load(); };
  const addSleep = async (hours, quality) => { await api.post("/health/sleep", { hours, quality }); ok("Sono registrado 😴"); load(); };
  const addNutrition = async (kcal, protein_g, label) => {
    await api.post("/health/nutrition", { kcal, protein_g, label });
    ok("Refeição registrada 🍽️"); load();
  };

  const connectWatch = async () => {
    // Simula sincronização de um smartwatch (BPM e kcal perdida)
    const bpm = 60 + Math.floor(Math.random() * 40);
    const kcal_burned = Math.round(50 + Math.random() * 250);
    await api.post("/health/device-sync", { bpm, kcal_burned, device_name: "Smartwatch" });
    ok(`Relógio sincronizado: ${bpm} bpm, ${kcal_burned} kcal`);
    load();
  };

  const connectFitbit = async () => {
    try {
      const { data } = await api.get("/health/fitbit/connect");
      window.location.href = data.url;
    } catch (e) {
      ok(e.response?.data?.detail || "Erro ao iniciar conexão com Fitbit");
    }
  };

  const syncFitbit = async () => {
    setFitbitBusy(true);
    try {
      const { data } = await api.post("/health/fitbit/sync");
      ok(data.synced?.length ? "Fitbit sincronizado ⌚" : (data.message || "Nada novo do Fitbit"));
      load();
    } catch (e) {
      ok(e.response?.data?.detail || "Erro ao sincronizar com o Fitbit");
    }
    setFitbitBusy(false);
  };

  const disconnectFitbit = async () => {
    await api.post("/health/fitbit/disconnect");
    ok("Fitbit desconectado");
    load();
  };

  const connectStrava = async () => {
    try {
      const { data } = await api.get("/health/strava/connect");
      window.location.href = data.url;
    } catch (e) {
      ok(e.response?.data?.detail || "Erro ao iniciar conexão com Strava");
    }
  };

  const syncStrava = async () => {
    setStravaBusy(true);
    try {
      const { data } = await api.post("/health/strava/sync");
      ok(data.synced?.length ? "Strava sincronizado 🏃" : (data.message || "Nada novo do Strava"));
      load();
    } catch (e) {
      ok(e.response?.data?.detail || "Erro ao sincronizar com o Strava");
    }
    setStravaBusy(false);
  };

  const disconnectStrava = async () => {
    await api.post("/health/strava/disconnect");
    ok("Strava desconectado");
    load();
  };

  // ---- Pedômetro do celular (acelerômetro via DeviceMotion) ----
  const [pedoSupported] = useState(typeof window !== "undefined" && "DeviceMotionEvent" in window);
  const [pedoTracking, setPedoTracking] = useState(false);
  const [pedoSteps, setPedoSteps] = useState(0);
  const pedoStateRef = useRef({ lastMag: 9.8, lastStepAt: 0 });

  const handleMotion = useCallback((e) => {
    const acc = e.accelerationIncludingGravity;
    if (!acc || acc.x == null) return;
    const mag = Math.sqrt(acc.x * acc.x + acc.y * acc.y + acc.z * acc.z);
    const st = pedoStateRef.current;
    const smoothed = st.lastMag * 0.9 + mag * 0.1;
    const delta = mag - smoothed;
    const now = Date.now();
    if (delta > 3.5 && now - st.lastStepAt > 300) {
      st.lastStepAt = now;
      setPedoSteps((s) => s + 1);
    }
    st.lastMag = smoothed;
  }, []);

  useEffect(() => () => window.removeEventListener("devicemotion", handleMotion), [handleMotion]);

  const startPedometer = async () => {
    if (!pedoSupported) { ok("Seu navegador/celular não suporta o sensor de movimento"); return; }
    if (typeof DeviceMotionEvent.requestPermission === "function") {
      try {
        const perm = await DeviceMotionEvent.requestPermission();
        if (perm !== "granted") { ok("Permissão de movimento negada"); return; }
      } catch (e) {
        ok("Não foi possível pedir permissão de movimento");
        return;
      }
    }
    pedoStateRef.current = { lastMag: 9.8, lastStepAt: 0 };
    setPedoSteps(0);
    window.addEventListener("devicemotion", handleMotion);
    setPedoTracking(true);
    ok("Pedômetro ativado — deixe o celular no bolso e caminhe 🚶");
  };

  const stopPedometer = async (save) => {
    window.removeEventListener("devicemotion", handleMotion);
    setPedoTracking(false);
    if (save && pedoSteps > 0) {
      const km = Math.round(pedoSteps * 0.0007 * 100) / 100; // ~0,7m por passo
      await api.post("/health/activity", { km, steps: pedoSteps, source: "phone" });
      ok(`${pedoSteps} passos registrados 🚶`);
      load();
    }
  };

  const [mealKcal, setMealKcal] = useState("");
  const [mealProtein, setMealProtein] = useState("");
  const [mealLabel, setMealLabel] = useState("");

  const submitMeal = async (e) => {
    e.preventDefault();
    if (mealKcal === "") return;
    await addNutrition(Number(mealKcal) || 0, Number(mealProtein) || 0, mealLabel || undefined);
    setMealKcal(""); setMealProtein(""); setMealLabel("");
  };

  const [sleepHours, setSleepHours] = useState("");
  const [sleepQuality, setSleepQuality] = useState("");

  const submitSleep = async (e) => {
    e.preventDefault();
    if (sleepHours === "") return;
    await addSleep(Number(sleepHours), sleepQuality || undefined);
    setSleepHours(""); setSleepQuality("");
  };

  const [editingGoals, setEditingGoals] = useState(false);
  const [goalForm, setGoalForm] = useState(null);

  const openGoals = () => {
    setGoalForm({ ...today.goals });
    setEditingGoals(true);
  };

  const saveGoals = async (e) => {
    e.preventDefault();
    await api.put("/health/goals", {
      water_l: Number(goalForm.water_l) || 0,
      kcal_in: Number(goalForm.kcal_in) || 0,
      protein_g: Number(goalForm.protein_g) || 0,
      km: Number(goalForm.km) || 0,
    });
    setEditingGoals(false);
    ok("Metas atualizadas 🎯");
    load();
  };

  if (loading) return <div className="shell"><div className="card-auth"><h1 className="display">Carregando…</h1></div></div>;

  const balance = (today.kcal_in - today.kcal_out).toFixed(0);
  const goals = today.goals || {};

  return (
    <div className="health-view" data-testid="health-view">
      <div className="health-header">
        <h1 className="display">Minha Saúde</h1>
        <div style={{ display: "flex", gap: ".5rem" }}>
          <button className="btn btn-ghost btn-sm" onClick={openGoals} data-testid="edit-goals-btn">🎯 Metas</button>
          <button className="btn btn-gold btn-sm" onClick={connectWatch} data-testid="connect-watch-btn">⌚ Simular relógio</button>
        </div>
      </div>

      <div className="health-forms" style={{ marginBottom: "1.2rem" }}>
        <div className="health-card" data-testid="fitbit-card">
          <h3>⌚ Fitbit</h3>
          {!fitbit.configured && (
            <p style={{ color: "var(--text-dim)", fontSize: ".85rem" }}>
              Integração ainda não configurada no servidor (faltam credenciais do Fitbit).
            </p>
          )}
          {fitbit.configured && !fitbit.connected && (
            <button className="btn btn-primary btn-sm" onClick={connectFitbit} data-testid="fitbit-connect-btn">
              Conectar minha conta Fitbit
            </button>
          )}
          {fitbit.configured && fitbit.connected && (
            <div style={{ display: "flex", gap: ".5rem", alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ color: "var(--gold)", fontSize: ".85rem" }}>✓ Conectado</span>
              <button className="btn btn-gold btn-sm" onClick={syncFitbit} disabled={fitbitBusy} data-testid="fitbit-sync-btn">
                {fitbitBusy ? "Sincronizando…" : "Sincronizar agora"}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={disconnectFitbit} data-testid="fitbit-disconnect-btn">
                Desconectar
              </button>
            </div>
          )}
        </div>

        <div className="health-card" data-testid="strava-card">
          <h3>🏃 Strava</h3>
          {!strava.configured && (
            <p style={{ color: "var(--text-dim)", fontSize: ".85rem" }}>
              Integração ainda não configurada no servidor (faltam credenciais do Strava).
            </p>
          )}
          {strava.configured && !strava.connected && (
            <button className="btn btn-primary btn-sm" onClick={connectStrava} data-testid="strava-connect-btn">
              Conectar minha conta Strava
            </button>
          )}
          {strava.configured && strava.connected && (
            <div style={{ display: "flex", gap: ".5rem", alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ color: "var(--gold)", fontSize: ".85rem" }}>✓ Conectado</span>
              <button className="btn btn-gold btn-sm" onClick={syncStrava} disabled={stravaBusy} data-testid="strava-sync-btn">
                {stravaBusy ? "Sincronizando…" : "Sincronizar agora"}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={disconnectStrava} data-testid="strava-disconnect-btn">
                Desconectar
              </button>
            </div>
          )}
        </div>

        <div className="health-card" data-testid="pedometer-card">
          <h3>📱 Pedômetro do celular</h3>
          {!pedoSupported && (
            <p style={{ color: "var(--text-dim)", fontSize: ".85rem" }}>
              Sensor de movimento não disponível neste navegador.
            </p>
          )}
          {pedoSupported && !pedoTracking && (
            <>
              <button className="btn btn-primary btn-sm" onClick={startPedometer} data-testid="pedometer-start-btn">
                Iniciar caminhada
              </button>
              <p style={{ color: "var(--text-dim)", fontSize: ".78rem", marginTop: ".4rem" }}>
                Deixe o celular no bolso/mão e caminhe. Ao terminar, toque em "Parar e salvar".
              </p>
            </>
          )}
          {pedoTracking && (
            <div>
              <div className="health-stat-value" style={{ marginBottom: ".4rem" }} data-testid="pedometer-live-count">
                {pedoSteps}<span className="health-stat-unit"> passos</span>
              </div>
              <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
                <button className="btn btn-gold btn-sm" onClick={() => stopPedometer(true)} data-testid="pedometer-stop-save-btn">
                  Parar e salvar
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => stopPedometer(false)} data-testid="pedometer-stop-discard-btn">
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {editingGoals && goalForm && (
        <form className="health-card" onSubmit={saveGoals} data-testid="form-goals" style={{ marginBottom: "1.2rem" }}>
          <h3>Metas diárias</h3>
          <div className="health-quickform">
            <input className="health-input" type="number" min="0" step="0.1" placeholder="Água (L)" value={goalForm.water_l} onChange={(e) => setGoalForm({ ...goalForm, water_l: e.target.value })} />
            <input className="health-input" type="number" min="0" placeholder="Kcal" value={goalForm.kcal_in} onChange={(e) => setGoalForm({ ...goalForm, kcal_in: e.target.value })} />
            <input className="health-input" type="number" min="0" placeholder="Proteína (g)" value={goalForm.protein_g} onChange={(e) => setGoalForm({ ...goalForm, protein_g: e.target.value })} />
            <input className="health-input" type="number" min="0" step="0.1" placeholder="Km" value={goalForm.km} onChange={(e) => setGoalForm({ ...goalForm, km: e.target.value })} />
            <button className="btn btn-primary btn-sm" type="submit">Salvar</button>
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => setEditingGoals(false)}>Cancelar</button>
          </div>
        </form>
      )}

      <div className="health-grid">
        <Stat label="Água" value={today.water_l} unit=" L" icon="💧" goal={goals.water_l} />
        <Stat label="BPM atual" value={today.last_bpm ?? "-"} unit="" icon="❤️" />
        <Stat label="Distância" value={today.km} unit=" km" icon="🚶" goal={goals.km} />
        <Stat label="Passos" value={today.steps} unit="" icon="👣" />
        <Stat label="Proteína" value={today.protein_g} unit=" g" icon="🥩" goal={goals.protein_g} />
        <Stat label="Kcal consumida" value={today.kcal_in} unit=" kcal" icon="🍽️" goal={goals.kcal_in} />
        <Stat label="Kcal perdida" value={today.kcal_out} unit=" kcal" icon="🔥" />
        <Stat label="Balanço calórico" value={balance} unit=" kcal" icon="⚖️" />
        <Stat label="Sono (última noite)" value={today.sleep_hours ?? "-"} unit={today.sleep_hours != null ? " h" : ""} icon="😴" />
      </div>

      <div className="health-forms">
        <div className="health-card">
          <h3>Água (L)</h3>
          <QuickForm testId="form-water" placeholder="ex: 0.5" step="0.1" buttonLabel="Adicionar" onSubmit={addWater} />
        </div>
        <div className="health-card">
          <h3>BPM</h3>
          <QuickForm testId="form-bpm" placeholder="ex: 72" buttonLabel="Registrar" onSubmit={addBpm} />
        </div>
        <div className="health-card">
          <h3>Distância (km)</h3>
          <QuickForm testId="form-km" placeholder="ex: 3.2" step="0.1" buttonLabel="Adicionar" onSubmit={addActivity} />
        </div>
        <div className="health-card">
          <h3>Kcal perdida (manual)</h3>
          <QuickForm testId="form-burned" placeholder="ex: 300" buttonLabel="Registrar" onSubmit={addBurned} />
        </div>
        <div className="health-card">
          <h3>Peso (kg)</h3>
          <QuickForm testId="form-weight" placeholder="ex: 72.5" step="0.1" buttonLabel="Registrar" onSubmit={addWeight} />
        </div>
        <div className="health-card health-card-wide">
          <h3>Refeição (proteína e kcal)</h3>
          <form className="health-quickform" onSubmit={submitMeal} data-testid="form-nutrition">
            <input className="health-input" placeholder="Ex: Almoço" value={mealLabel} onChange={(e) => setMealLabel(e.target.value)} />
            <input className="health-input" type="number" min="0" placeholder="kcal" value={mealKcal} onChange={(e) => setMealKcal(e.target.value)} />
            <input className="health-input" type="number" min="0" placeholder="proteína (g)" value={mealProtein} onChange={(e) => setMealProtein(e.target.value)} />
            <button className="btn btn-primary btn-sm" type="submit">Adicionar</button>
          </form>
        </div>
        <div className="health-card">
          <h3>Sono (última noite)</h3>
          <form className="health-quickform" onSubmit={submitSleep} data-testid="form-sleep">
            <input className="health-input" type="number" min="0" step="0.5" placeholder="horas" value={sleepHours} onChange={(e) => setSleepHours(e.target.value)} />
            <select className="health-input" value={sleepQuality} onChange={(e) => setSleepQuality(e.target.value)}>
              <option value="">Qualidade?</option>
              <option value="ruim">Ruim</option>
              <option value="ok">Ok</option>
              <option value="boa">Boa</option>
              <option value="otima">Ótima</option>
            </select>
            <button className="btn btn-primary btn-sm" type="submit">Registrar</button>
          </form>
        </div>
      </div>

      <div className="health-charts">
        <ChartCard title="Água (L)" unit=" L" points={history.map((d) => ({ date: d.date.slice(5), value: d.water_l }))} />
        <ChartCard title="Distância (km)" unit=" km" points={history.map((d) => ({ date: d.date.slice(5), value: d.km }))} />
        <ChartCard title="Kcal (in vs out)" unit=" kcal" points={history.map((d) => ({ date: d.date.slice(5), value: d.kcal_in }))} />
        <ChartCard title="BPM médio" points={history.map((d) => ({ date: d.date.slice(5), value: d.avg_bpm }))} />
        <ChartCard title="Peso (kg) — 30 dias" unit=" kg" points={weightHistory.map((w) => ({ date: w.date.slice(5), value: w.kg }))} />
        <ChartCard title="Sono (h) — 14 dias" unit=" h" points={sleepHistory.map((s) => ({ date: s.date.slice(5), value: s.hours }))} />
      </div>

      <div className="health-history">
        <h3>Últimos 7 dias</h3>
        <div className="health-history-table">
          <div className="health-history-row health-history-head">
            <span>Data</span><span>Água</span><span>Km</span><span>Proteína</span><span>Kcal in</span><span>Kcal out</span><span>BPM médio</span>
          </div>
          {history.map((d) => (
            <div className="health-history-row" key={d.date} data-testid="health-history-row">
              <span>{d.date.slice(5)}</span>
              <span>{d.water_l} L</span>
              <span>{d.km} km</span>
              <span>{d.protein_g} g</span>
              <span>{d.kcal_in}</span>
              <span>{d.kcal_out}</span>
              <span>{d.avg_bpm ?? "-"}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
