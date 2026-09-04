import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const api = axios.create({ baseURL: API, withCredentials: true });

function Stat({ label, value, unit, icon }) {
  return (
    <div className="health-stat" data-testid={`health-stat-${label}`}>
      <div className="health-stat-icon">{icon}</div>
      <div>
        <div className="health-stat-value">{value}<span className="health-stat-unit">{unit}</span></div>
        <div className="health-stat-label">{label}</div>
      </div>
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
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [t, h] = await Promise.all([
        api.get("/health/today"),
        api.get("/health/history?days=7"),
      ]);
      setToday(t.data);
      setHistory(h.data.days);
    } catch (e) {
      toast?.("Erro ao carregar dados de saúde");
    }
    setLoading(false);
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const ok = (msg) => toast?.(msg);

  const addWater = async (liters) => { await api.post("/health/water", { liters }); ok("Água registrada 💧"); load(); };
  const addBpm = async (bpm) => { await api.post("/health/bpm", { bpm, source: "manual" }); ok("BPM registrado ❤️"); load(); };
  const addActivity = async (km) => { await api.post("/health/activity", { km, source: "manual" }); ok("Caminhada registrada 🚶"); load(); };
  const addBurned = async (kcal) => { await api.post("/health/burned", { kcal, source: "manual" }); ok("Kcal perdida registrada 🔥"); load(); };
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

  const [mealKcal, setMealKcal] = useState("");
  const [mealProtein, setMealProtein] = useState("");
  const [mealLabel, setMealLabel] = useState("");

  const submitMeal = async (e) => {
    e.preventDefault();
    if (mealKcal === "") return;
    await addNutrition(Number(mealKcal) || 0, Number(mealProtein) || 0, mealLabel || undefined);
    setMealKcal(""); setMealProtein(""); setMealLabel("");
  };

  if (loading) return <div className="shell"><div className="card-auth"><h1 className="display">Carregando…</h1></div></div>;

  const balance = (today.kcal_in - today.kcal_out).toFixed(0);

  return (
    <div className="health-view" data-testid="health-view">
      <div className="health-header">
        <h1 className="display">Minha Saúde</h1>
        <button className="btn btn-gold btn-sm" onClick={connectWatch} data-testid="connect-watch-btn">⌚ Conectar relógio</button>
      </div>

      <div className="health-grid">
        <Stat label="Água" value={today.water_l} unit=" L" icon="💧" />
        <Stat label="BPM atual" value={today.last_bpm ?? "-"} unit="" icon="❤️" />
        <Stat label="Distância" value={today.km} unit=" km" icon="🚶" />
        <Stat label="Passos" value={today.steps} unit="" icon="👣" />
        <Stat label="Proteína" value={today.protein_g} unit=" g" icon="🥩" />
        <Stat label="Kcal consumida" value={today.kcal_in} unit=" kcal" icon="🍽️" />
        <Stat label="Kcal perdida" value={today.kcal_out} unit=" kcal" icon="🔥" />
        <Stat label="Balanço calórico" value={balance} unit=" kcal" icon="⚖️" />
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
        <div className="health-card health-card-wide">
          <h3>Refeição (proteína e kcal)</h3>
          <form className="health-quickform" onSubmit={submitMeal} data-testid="form-nutrition">
            <input className="health-input" placeholder="Ex: Almoço" value={mealLabel} onChange={(e) => setMealLabel(e.target.value)} />
            <input className="health-input" type="number" min="0" placeholder="kcal" value={mealKcal} onChange={(e) => setMealKcal(e.target.value)} />
            <input className="health-input" type="number" min="0" placeholder="proteína (g)" value={mealProtein} onChange={(e) => setMealProtein(e.target.value)} />
            <button className="btn btn-primary btn-sm" type="submit">Adicionar</button>
          </form>
        </div>
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
