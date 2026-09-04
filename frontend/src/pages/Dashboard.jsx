import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import RiskMap from "@/components/RiskMap";
import { api, severityClass } from "@/lib/api";
import { useNavigate } from "react-router-dom";
import { Warning, Lightning, ArrowClockwise } from "@phosphor-icons/react";

function Stat({ label, value, tone = "text-white", testid }) {
    return (
        <div className="tactical-card p-3" data-testid={testid}>
            <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">{label}</div>
            <div className={`font-heading text-2xl font-bold tracking-tighter ${tone}`}>{value}</div>
        </div>
    );
}

export default function Dashboard() {
    const nav = useNavigate();
    const [summary, setSummary] = useState(null);
    const [priorities, setPriorities] = useState([]);
    const [alerts, setAlerts] = useState([]);
    const [reports, setReports] = useState([]);
    const [running, setRunning] = useState(false);

    const load = async () => {
        const [s, p, a, r] = await Promise.all([
            api.get("/dashboard/summary"),
            api.get("/response/priorities"),
            api.get("/alerts"),
            api.get("/reports?limit=10"),
        ]);
        setSummary(s.data);
        setPriorities(p.data);
        setAlerts(a.data);
        setReports(r.data);
    };

    useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);

    const runAll = async () => {
        setRunning(true);
        try { await api.post("/predictions/run-all"); await load(); } finally { setRunning(false); }
    };

    if (!summary) return <Shell><div className="p-8 font-mono text-sm text-[var(--text-2)]">Loading operations console…</div></Shell>;

    const sc = summary.severity_counts;

    return (
        <Shell>
            <div className="grid grid-cols-12 lg:h-screen">
                <div className="col-span-12 lg:col-span-8 xl:col-span-9 flex flex-col">
                    <header className="tactical-border border-l-0 border-r-0 border-t-0 px-4 md:px-6 py-3 flex items-center justify-between gap-2 flex-wrap">
                        <div>
                            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Authority Dashboard · NER</div>
                            <div className="font-heading text-xl md:text-2xl tracking-tighter font-bold">Operations Overview</div>
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                            <div className="chip sev-low">
                                <span className="w-2 h-2 rounded-full bg-current" /> LIVE
                            </div>
                            <button onClick={runAll} disabled={running} data-testid="run-all-btn" className="px-3 py-1.5 tactical-border text-[11px] md:text-xs font-mono uppercase tracking-[0.15em] hover:bg-white/5 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                                <ArrowClockwise size={12} className={running ? "animate-spin" : ""} />
                                {running ? "Running" : "Run all"}
                            </button>
                        </div>
                    </header>

                    <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-2 px-4 md:px-6 py-3">
                        <Stat label="Total zones" value={summary.zones_total} testid="stat-zones" />
                        <Stat label="Critical" value={sc.CRITICAL} tone="text-[var(--sev-critical)]" testid="stat-critical" />
                        <Stat label="High" value={sc.HIGH} tone="text-[var(--sev-high)]" testid="stat-high" />
                        <Stat label="Medium" value={sc.MEDIUM} tone="text-[var(--sev-medium)]" testid="stat-medium" />
                        <Stat label="Low" value={sc.LOW} tone="text-[var(--sev-low)]" testid="stat-low" />
                        <Stat label="Sensors ●" value={`${summary.sensors_online}/${summary.sensors_online + summary.sensors_offline}`} testid="stat-sensors" />
                        <Stat label="Roads blocked" value={summary.roads_blocked} tone="text-[var(--sev-critical)]" testid="stat-roads" />
                        <Stat label="Active alerts" value={summary.active_alerts} tone="text-[var(--sev-high)]" testid="stat-alerts" />
                    </div>

                    <div className="px-4 md:px-6 pb-6 flex-1 min-h-0">
                        <div className="tactical-card overflow-hidden h-[60vh] lg:h-full">
                            <RiskMap
                                onSelectZone={(id) => nav(`/zones/${id}`)}
                                reports={reports}
                                height="100%"
                            />
                        </div>
                    </div>
                </div>

                <aside className="col-span-12 lg:col-span-4 xl:col-span-3 border-t lg:border-t-0 lg:border-l border-[var(--border)] lg:h-screen overflow-y-auto p-4 space-y-4">
                    <section data-testid="priority-list">
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-2">
                            <Warning size={14} /> Response Priorities
                        </h2>
                        <div className="space-y-2">
                            {priorities.slice(0, 8).map((p) => (
                                <button
                                    key={p.zone_id}
                                    onClick={() => nav(`/zones/${p.zone_id}`)}
                                    data-testid={`priority-${p.zone_id}`}
                                    className="w-full text-left tactical-card p-3 hover:bg-white/[0.03] transition-colors"
                                >
                                    <div className="flex items-center justify-between">
                                        <span className={`chip ${p.priority === "P1" ? "sev-critical" : p.priority === "P2" ? "sev-high" : p.priority === "P3" ? "sev-medium" : "sev-low"} ${p.priority === "P1" ? "pulse-critical" : ""}`}>
                                            {p.priority} · {p.label}
                                        </span>
                                        <span className="font-mono text-[10px] text-[var(--text-2)]">{p.severity}</span>
                                    </div>
                                    <div className="font-heading text-sm mt-1.5">{p.zone_name}</div>
                                    <div className="font-mono text-[10px] text-[var(--text-2)]">{p.district}, {p.state} · score {p.score}</div>
                                </button>
                            ))}
                            {!priorities.length && <div className="text-xs font-mono text-[var(--text-2)]">No priorities yet. Click "Run risk over all zones".</div>}
                        </div>
                    </section>

                    <section data-testid="alerts-list">
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-2">
                            <Lightning size={14} /> Recent Alerts
                        </h2>
                        <div className="space-y-2">
                            {alerts.slice(0, 5).map((a) => (
                                <div key={a.id} className="tactical-card p-3">
                                    <span className={`chip ${severityClass(a.severity)}`}>{a.severity}</span>
                                    <div className="font-mono text-[11px] mt-1 line-clamp-3">{a.translations?.en || a.reason}</div>
                                </div>
                            ))}
                            {!alerts.length && <div className="text-xs font-mono text-[var(--text-2)]">No alerts issued yet.</div>}
                        </div>
                    </section>
                </aside>
            </div>
        </Shell>
    );
}
