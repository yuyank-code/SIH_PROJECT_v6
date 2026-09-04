import { useParams, useNavigate } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, severityClass, SEVERITY_COLORS } from "@/lib/api";
import { CloudRain, MapPin, Path, Buildings, Broadcast, Lightning, ArrowLeft, ArrowClockwise, ShieldWarning } from "@phosphor-icons/react";

function Field({ label, value, unit }) {
    return (
        <div className="tactical-card p-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">{label}</div>
            <div className="font-mono text-lg">{value}{unit ? <span className="text-xs text-[var(--text-2)] ml-1">{unit}</span> : null}</div>
        </div>
    );
}

export default function ZoneDetail() {
    const { id } = useParams();
    const nav = useNavigate();
    const [zone, setZone] = useState(null);
    const [weather, setWeather] = useState(null);
    const [explanation, setExplanation] = useState("");
    const [simulateRainX, setSimulateRainX] = useState(1);
    const [issuing, setIssuing] = useState(false);
    const [running, setRunning] = useState(false);

    const load = useCallback(async () => {
        const { data } = await api.get(`/zones/${id}`);
        setZone(data);
        try {
            const w = await api.get("/weather", { params: { latitude: data.centroid.lat, longitude: data.centroid.lon } });
            setWeather(w.data);
        } catch {}
        if (data.latest?.contributing_factors) {
            const ex = await api.post("/explain", {
                severity: data.latest.severity,
                factors: data.latest.contributing_factors,
                zone_name: data.name,
            });
            setExplanation(ex.data.explanation);
        }
    }, [id]);
    useEffect(() => { load(); }, [load]);

    const runPrediction = async (multiplier = 1) => {
        setRunning(true);
        try {
            const body = { zone_id: id };
            if (multiplier !== 1 && zone?.latest?.features_used) {
                const f = { ...zone.latest.features_used };
                for (const k of ["rainfall_1d", "rainfall_3d", "rainfall_7d", "rainfall_15d", "rainfall_30d", "max_rainfall_3d", "max_rainfall_7d"]) {
                    f[k] = (f[k] || 0) * multiplier;
                }
                body.rainfall_override = {
                    rainfall_1d: f.rainfall_1d, rainfall_3d: f.rainfall_3d, rainfall_7d: f.rainfall_7d,
                    rainfall_15d: f.rainfall_15d, rainfall_30d: f.rainfall_30d,
                    max_rainfall_3d: f.max_rainfall_3d, max_rainfall_7d: f.max_rainfall_7d,
                    rainy_days_7d: f.rainy_days_7d,
                };
            }
            await api.post("/predictions/zone", body);
            await load();
        } finally { setRunning(false); }
    };

    const issueAlert = async () => {
        if (!zone?.latest) return;
        setIssuing(true);
        try {
            await api.post("/alerts", {
                zone_id: zone.zone_id,
                severity: zone.latest.severity,
                reason: (zone.latest.contributing_factors || []).map((f) => `${f.label} ${f.value}${f.unit}`).join("; ") || "combined rainfall + terrain",
                recommended_action: "Evacuate at-risk slopes; halt roadside construction; notify local authorities.",
            });
            await load();
        } finally { setIssuing(false); }
    };

    if (!zone) return <Shell><div className="p-8 font-mono text-sm text-[var(--text-2)]">Loading zone…</div></Shell>;
    const sev = zone.latest?.severity || "UNKNOWN";

    return (
        <Shell>
            <div className="p-6 max-w-6xl mx-auto space-y-5" data-testid="zone-detail">
                <button onClick={() => nav(-1)} className="font-mono text-xs uppercase tracking-[0.15em] text-[var(--text-2)] hover:text-white flex items-center gap-1" data-testid="back-btn">
                    <ArrowLeft size={12} /> Back
                </button>

                <header className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">{zone.state} · {zone.district}</div>
                        <h1 className="font-heading text-3xl md:text-4xl tracking-tighter font-bold">{zone.name}</h1>
                        <div className="font-mono text-xs text-[var(--text-2)] mt-1">
                            <MapPin size={11} className="inline mr-1" /> {zone.centroid.lat.toFixed(4)}, {zone.centroid.lon.toFixed(4)}
                            {" · "}Terrain source: <span className="text-white">{zone.terrain_source}</span>
                        </div>
                    </div>
                    <div className="text-right">
                        <span className={`chip ${severityClass(sev)} ${sev === "CRITICAL" ? "pulse-critical" : ""}`} data-testid="zone-severity">{sev}</span>
                        <div className="font-mono text-3xl font-bold mt-1" style={{ color: SEVERITY_COLORS[sev] || "#fff" }}>{zone.latest?.risk_score ?? "—"}</div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">Risk score / 100</div>
                    </div>
                </header>

                <div className="flex items-center gap-2 flex-wrap">
                    <button onClick={() => runPrediction(1)} disabled={running} data-testid="run-prediction-btn" className="px-3 py-1.5 tactical-border text-xs font-mono uppercase tracking-[0.15em] hover:bg-white/5 flex items-center gap-1.5 disabled:opacity-50">
                        <ArrowClockwise size={12} className={running ? "animate-spin" : ""} /> Run V5 prediction
                    </button>
                    <div className="flex items-center gap-2 tactical-border px-3 py-1.5">
                        <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">Simulate rainfall</span>
                        <input type="range" min="1" max="4" step="0.25" value={simulateRainX} onChange={(e) => setSimulateRainX(parseFloat(e.target.value))} className="w-24" data-testid="simulate-rain-slider" />
                        <span className="font-mono text-xs">{simulateRainX.toFixed(2)}×</span>
                        <button onClick={() => runPrediction(simulateRainX)} disabled={running || !zone.latest} data-testid="simulate-run-btn" className="text-xs font-mono uppercase tracking-[0.15em] text-[var(--sev-high)] hover:underline disabled:opacity-50">
                            Apply
                        </button>
                    </div>
                    <button onClick={issueAlert} disabled={issuing || !zone.latest} data-testid="issue-alert-btn" className="ml-auto px-3 py-1.5 bg-[var(--sev-critical)] text-white text-xs font-mono uppercase tracking-[0.15em] hover:bg-red-500 flex items-center gap-1.5 disabled:opacity-50">
                        <Lightning size={12} /> {issuing ? "Issuing…" : "Issue multilingual alert"}
                    </button>
                </div>

                {explanation && (
                    <div className="tactical-card p-4 border-l-2 border-[var(--sev-high)]" data-testid="risk-explanation">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-1 flex items-center gap-1.5">
                            <ShieldWarning size={12} /> Why is this zone at risk?
                        </div>
                        <p className="font-body text-sm leading-relaxed">{explanation}</p>
                    </div>
                )}

                <section>
                    <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5">
                        <CloudRain size={14} /> Rainfall drivers (Open-Meteo)
                    </h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        {zone.latest?.features_used ? (
                            <>
                                <Field label="Rain 1d" value={zone.latest.features_used.rainfall_1d} unit="mm" />
                                <Field label="Rain 3d" value={zone.latest.features_used.rainfall_3d} unit="mm" />
                                <Field label="Rain 7d" value={zone.latest.features_used.rainfall_7d} unit="mm" />
                                <Field label="Rain 15d" value={zone.latest.features_used.rainfall_15d} unit="mm" />
                                <Field label="Rain 30d" value={zone.latest.features_used.rainfall_30d} unit="mm" />
                                <Field label="Peak 3d in 30d" value={zone.latest.features_used.max_rainfall_3d} unit="mm" />
                                <Field label="Peak 7d in 30d" value={zone.latest.features_used.max_rainfall_7d} unit="mm" />
                                <Field label="Rainy days /7" value={zone.latest.features_used.rainy_days_7d} unit="d" />
                            </>
                        ) : <div className="text-xs font-mono text-[var(--text-2)]">Run a prediction to load rainfall features.</div>}
                    </div>
                </section>

                <section>
                    <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2">Terrain (DEMO)</h2>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                        <Field label="Elevation" value={zone.terrain.elevation_m} unit="m" />
                        <Field label="Slope" value={zone.terrain.slope_deg} unit="°" />
                        <Field label="Aspect sin" value={zone.terrain.aspect_sin} />
                        <Field label="Aspect cos" value={zone.terrain.aspect_cos} />
                        <Field label="Curvature" value={zone.terrain.curvature_1_m} unit="1/m" />
                    </div>
                </section>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <section>
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5">
                            <Path size={14} /> Nearby roads
                        </h2>
                        <div className="space-y-1">
                            {zone.roads_nearby?.map((r) => (
                                <div key={r.road_id} className="tactical-card p-2 flex items-center justify-between">
                                    <span className="text-sm">{r.name}</span>
                                    <span className={`chip ${r.status === "BLOCKED" ? "sev-critical" : r.status === "AT_RISK" ? "sev-medium" : "sev-low"}`}>{r.status}</span>
                                    <span className="font-mono text-[10px] text-[var(--text-2)]">{r.distance_km} km</span>
                                </div>
                            ))}
                        </div>
                    </section>
                    <section>
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5">
                            <Buildings size={14} /> Nearby villages
                        </h2>
                        <div className="space-y-1">
                            {zone.villages_nearby?.map((v) => (
                                <div key={v.village_id} className="tactical-card p-2 flex items-center justify-between">
                                    <span className="text-sm">{v.name}</span>
                                    <span className="font-mono text-[10px] text-[var(--text-2)]">pop {v.population}</span>
                                    <span className="font-mono text-[10px] text-[var(--text-2)]">{v.distance_km} km</span>
                                </div>
                            ))}
                        </div>
                    </section>
                </div>

                <section>
                    <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5">
                        <Broadcast size={14} /> Sensors in zone
                    </h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        {zone.sensors?.map((s) => (
                            <div key={s.sensor_id} className="tactical-card p-3">
                                <div className="flex items-center justify-between">
                                    <span className="font-mono text-xs">{s.sensor_id}</span>
                                    <span className={`chip ${s.status === "ONLINE" ? "sev-low" : "sev-unknown"}`}>{s.status}</span>
                                </div>
                                <div className="text-sm mt-1">{s.type}</div>
                                <div className="font-mono text-[10px] text-[var(--text-2)]">Battery {s.battery}%</div>
                            </div>
                        ))}
                        {!zone.sensors?.length && <div className="text-xs font-mono text-[var(--text-2)]">No sensors placed in this zone.</div>}
                    </div>
                </section>

                {zone.latest?.contributing_factors?.length ? (
                    <section>
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2">Contributing factors (V5 importance-weighted)</h2>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            {zone.latest.contributing_factors.map((f) => (
                                <div key={f.feature} className="tactical-card p-3 flex items-center justify-between">
                                    <div>
                                        <div className="text-sm">{f.label}</div>
                                        <div className="font-mono text-[10px] text-[var(--text-2)]">{f.feature}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="font-mono text-lg">{f.value}<span className="text-[10px] text-[var(--text-2)] ml-1">{f.unit}</span></div>
                                        <div className="font-mono text-[10px] text-[var(--text-2)]">imp {(f.importance * 100).toFixed(2)}</div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                ) : null}
            </div>
        </Shell>
    );
}
