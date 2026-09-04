import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import Shell from "@/components/Shell";
import { api, severityClass } from "@/lib/api";
import { PaperPlaneTilt, Path, Warning, CheckCircle, ArrowRight, XCircle } from "@phosphor-icons/react";

// Feature A — Rapid dispatch & routing (plus the existing P1-P4 prioritization).
// Dispatching a zone hits POST /response/dispatch, which attaches the nearest
// roads and flags any BLOCKED/RESTRICTED segments (access derived purely from
// stored road status). Tasks then move through PENDING -> DISPATCHED -> EN_ROUTE
// -> ON_SITE -> RESOLVED on the board below.
const FLOW = ["PENDING", "DISPATCHED", "EN_ROUTE", "ON_SITE", "RESOLVED"];
const taskChip = (s) => ({
    PENDING: "sev-medium", DISPATCHED: "sev-high", EN_ROUTE: "sev-high",
    ON_SITE: "sev-critical", RESOLVED: "sev-low", CANCELLED: "sev-unknown", OPEN: "sev-medium",
}[s] || "sev-unknown");

export default function Response() {
    const nav = useNavigate();
    const [items, setItems] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [dispatching, setDispatching] = useState(null);

    const loadTasks = useCallback(async () => {
        const r = await api.get("/response/tasks?phase=RESPONSE");
        setTasks(r.data);
    }, []);

    useEffect(() => {
        api.get("/response/priorities").then(r => setItems(r.data));
        loadTasks();
    }, [loadTasks]);

    const dispatch = async (zone) => {
        setDispatching(zone.zone_id);
        try {
            await api.post("/response/dispatch", { zone_id: zone.zone_id, title: `Dispatch to ${zone.zone_name}` });
            await loadTasks();
        } finally { setDispatching(null); }
    };

    const advance = async (t) => {
        const idx = FLOW.indexOf(t.status);
        const next = idx >= 0 && idx < FLOW.length - 1 ? FLOW[idx + 1] : "RESOLVED";
        await api.patch(`/response/tasks/${t.id}`, { status: next });
        await loadTasks();
    };
    const cancel = async (t) => { await api.patch(`/response/tasks/${t.id}`, { status: "CANCELLED" }); await loadTasks(); };

    const activeTasks = tasks.filter(t => !["RESOLVED", "CANCELLED"].includes(t.status));
    const doneTasks = tasks.filter(t => ["RESOLVED", "CANCELLED"].includes(t.status));

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="response-page">
                <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Response prioritization</div>
                    <h1 className="font-heading text-3xl tracking-tighter font-bold">Where to respond first</h1>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                    {["P1", "P2", "P3", "P4"].map(pkey => (
                        <div key={pkey} className="tactical-card p-3" data-testid={`col-${pkey}`}>
                            <div className={`chip ${pkey === "P1" ? "sev-critical pulse-critical" : pkey === "P2" ? "sev-high" : pkey === "P3" ? "sev-medium" : "sev-low"}`}>{pkey}</div>
                            <div className="space-y-2 mt-3">
                                {items.filter(i => i.priority === pkey).map(i => (
                                    <div key={i.zone_id} className="border border-[var(--border)] p-2 hover:bg-white/[0.03]">
                                        <div onClick={() => nav(`/zones/${i.zone_id}`)} className="cursor-pointer">
                                            <div className="font-heading text-sm">{i.zone_name}</div>
                                            <div className="font-mono text-[10px] text-[var(--text-2)]">{i.district}, {i.state}</div>
                                            <div className="flex items-center gap-2 mt-1">
                                                <span className={`chip ${severityClass(i.severity)}`}>{i.severity}</span>
                                                <span className="font-mono text-[10px]">score {i.score}</span>
                                            </div>
                                            {i.unknown_factors?.length ? <div className="font-mono text-[10px] text-[var(--sev-medium)] mt-1">Missing: {i.unknown_factors.join(", ")}</div> : null}
                                        </div>
                                        <button onClick={() => dispatch(i)} disabled={dispatching === i.zone_id} data-testid={`dispatch-${i.zone_id}`} className="mt-2 w-full py-1 bg-[var(--sev-critical)] text-white text-[10px] font-mono uppercase tracking-[0.1em] hover:bg-red-500 disabled:opacity-50 flex items-center justify-center gap-1">
                                            <PaperPlaneTilt size={11} /> {dispatching === i.zone_id ? "Dispatching…" : "Dispatch team"}
                                        </button>
                                    </div>
                                ))}
                                {!items.filter(i => i.priority === pkey).length && <div className="font-mono text-[10px] text-[var(--text-2)]">— none —</div>}
                            </div>
                        </div>
                    ))}
                </div>

                <section>
                    <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5"><PaperPlaneTilt size={14} /> Dispatch board · active ({activeTasks.length})</h2>
                    <div className="tactical-card divide-y divide-[var(--border)]" data-testid="task-board">
                        {activeTasks.map(t => {
                            const route = t.route || {};
                            const blocked = route.blocked_segments || [];
                            return (
                                <div key={t.id} className="p-3" data-testid={`task-${t.id}`}>
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className={`chip ${taskChip(t.status)}`}>{t.status}</span>
                                        {t.priority && <span className="chip sev-unknown font-mono text-[10px]">{t.priority}</span>}
                                        <span className="font-heading text-sm">{t.title}</span>
                                        <span className="font-mono text-[10px] text-[var(--text-2)]">{t.zone_name || t.zone_code} · team {t.team || "—"}</span>
                                        {route.access && (
                                            <span className={`chip ${route.access === "IMPACTED" ? "sev-high" : route.access === "CLEAR" ? "sev-low" : "sev-unknown"}`}>
                                                <Path size={11} /> {route.access}
                                            </span>
                                        )}
                                        <div className="ml-auto flex items-center gap-1.5">
                                            {t.status !== "RESOLVED" && (
                                                <button onClick={() => advance(t)} data-testid={`advance-${t.id}`} className="chip sev-high hover:text-white">
                                                    {FLOW.indexOf(t.status) >= FLOW.length - 1 ? <><CheckCircle size={11} /> Resolve</> : <><ArrowRight size={11} /> {FLOW[FLOW.indexOf(t.status) + 1] || "RESOLVED"}</>}
                                                </button>
                                            )}
                                            <button onClick={() => cancel(t)} data-testid={`cancel-${t.id}`} className="chip sev-unknown hover:text-[var(--sev-critical)]"><XCircle size={11} /></button>
                                        </div>
                                    </div>
                                    {blocked.length > 0 && (
                                        <div className="mt-1.5 flex items-start gap-1.5 text-[var(--sev-high)]" data-testid={`blocked-${t.id}`}>
                                            <Warning size={12} className="mt-0.5" />
                                            <div className="font-mono text-[10px]">Blocked on route: {blocked.map(b => b.name || b.road_id).join(", ")}</div>
                                        </div>
                                    )}
                                    {route.nearest_roads?.length ? (
                                        <div className="mt-1 font-mono text-[10px] text-[var(--text-2)]">
                                            Nearest: {route.nearest_roads.slice(0, 3).map(r => `${r.name || r.road_id} (${r.status}${r.distance_km != null ? `, ${r.distance_km}km` : ""})`).join(" · ")}
                                        </div>
                                    ) : null}
                                </div>
                            );
                        })}
                        {!activeTasks.length && <div className="p-6 font-mono text-xs text-[var(--text-2)] text-center">No active dispatches. Use "Dispatch team" on a prioritized zone above.</div>}
                    </div>
                </section>

                {doneTasks.length > 0 && (
                    <section>
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 text-[var(--text-2)]">Closed ({doneTasks.length})</h2>
                        <div className="tactical-card divide-y divide-[var(--border)]" data-testid="task-board-closed">
                            {doneTasks.map(t => (
                                <div key={t.id} className="p-2.5 flex items-center gap-2 opacity-70" data-testid={`task-done-${t.id}`}>
                                    <span className={`chip ${taskChip(t.status)}`}>{t.status}</span>
                                    <span className="font-heading text-sm flex-1 truncate">{t.title}</span>
                                    <span className="font-mono text-[10px] text-[var(--text-2)]">{t.zone_name || t.zone_code}</span>
                                    {t.resolved_at && <span className="font-mono text-[9px] text-[var(--text-2)]">{new Date(t.resolved_at).toLocaleString()}</span>}
                                </div>
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </Shell>
    );
}
