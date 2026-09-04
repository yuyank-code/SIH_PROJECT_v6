import { useEffect, useState, useCallback } from "react";
import Shell from "@/components/Shell";
import { api, severityClass } from "@/lib/api";
import { Broadcast, PaperPlaneTilt, Warning, FileText, Path, ArrowClockwise, Pulse, Waveform, WarningCircle } from "@phosphor-icons/react";

// Feature B — Live operations board ("what's happening now").
// Pure composition of existing signals: GET /ops/summary (counters) and
// GET /ops/activity (merged, timestamped event feed). Auto-refreshes so a demo
// feels live; each event carries its own kind + source tag (no fabricated data).
//
// v4 adds the Watchboard: the existing per-zone predictions turned into an
// operational watch picture — what to DO (warning/watch/advisory), whether
// rainfall is rising, and whether the prediction is fresh enough to trust.
// All computed server-side in monitoring_service from stored prediction
// features, so nothing here is invented.
const KIND = {
    ALERT: { icon: Broadcast, label: "Alert", cls: "sev-critical" },
    RESPONSE_TASK: { icon: PaperPlaneTilt, label: "Dispatch", cls: "sev-high" },
    INCIDENT: { icon: Warning, label: "Incident", cls: "sev-high" },
    REPORT: { icon: FileText, label: "Field report", cls: "sev-medium" },
    ROAD: { icon: Path, label: "Road", cls: "sev-medium" },
};

const WATCH = {
    WARNING: { cls: "sev-critical", label: "Warning" },
    WATCH: { cls: "sev-high", label: "Watch" },
    ADVISORY: { cls: "sev-medium", label: "Advisory" },
    STAND_DOWN: { cls: "sev-unknown", label: "Stand down" },
};

const TREND = { RISING: "\u25B4", FALLING: "\u25BE", STEADY: "\u2013", UNKNOWN: "\u2013" }; // ▲ ▼ – –
const trendTone = (t) => ({ RISING: "text-[var(--sev-critical)]", FALLING: "text-[var(--sev-low)]" }[t] || "text-[var(--text-2)]");

const timeAgo = (iso) => {
    if (!iso) return "";
    const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
};

function Tile({ label, value, tone }) {
    return (
        <div className="tactical-card p-3" data-testid={`tile-${label.replace(/\s+/g, "-").toLowerCase()}`}>
            <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-[var(--text-2)]">{label}</div>
            <div className={`font-heading text-2xl font-bold ${tone || ""}`}>{value}</div>
        </div>
    );
}

export default function OpsBoard() {
    const [summary, setSummary] = useState(null);
    const [feed, setFeed] = useState([]);
    const [updated, setUpdated] = useState(null);
    const [watch, setWatch] = useState([]);
    const [watchSum, setWatchSum] = useState(null);
    const [onlyActionable, setOnlyActionable] = useState(false);

    const load = useCallback(async () => {
        const [s, a, w, ws] = await Promise.all([
            api.get("/ops/summary"),
            api.get("/ops/activity?limit=80"),
            api.get("/monitoring/watchboard"),
            api.get("/monitoring/summary"),
        ]);
        setSummary(s.data);
        setFeed(a.data);
        setWatch(w.data);
        setWatchSum(ws.data);
        setUpdated(new Date());
    }, []);

    useEffect(() => {
        load();
        const id = setInterval(load, 20000); // live-ish refresh for the ops room
        return () => clearInterval(id);
    }, [load]);

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="ops-board-page">
                <div className="flex items-center gap-3 flex-wrap">
                    <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Operations</div>
                        <h1 className="font-heading text-3xl tracking-tighter font-bold">What's happening now</h1>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                        {updated && <span className="font-mono text-[10px] text-[var(--text-2)]">updated {updated.toLocaleTimeString()}</span>}
                        <button onClick={load} data-testid="ops-refresh" className="chip sev-unknown hover:text-white"><ArrowClockwise size={12} /> Refresh</button>
                    </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
                    <Tile label="Zones on warning" value={watchSum?.by_level?.WARNING ?? "—"} tone="text-[var(--sev-critical)]" />
                    <Tile label="Active incidents" value={summary?.active_incidents ?? "—"} tone="text-[var(--sev-high)]" />
                    <Tile label="Open tasks" value={summary?.open_tasks ?? "—"} />
                    <Tile label="Active alerts" value={summary?.active_alerts ?? "—"} tone="text-[var(--sev-critical)]" />
                    <Tile label="Roads blocked" value={summary?.roads_blocked ?? "—"} tone="text-[var(--sev-high)]" />
                    <Tile label="Sensors online" value={summary != null ? `${summary.sensors_online}/${summary.sensors_online + summary.sensors_offline}` : "—"} />
                </div>

                <section>
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold flex items-center gap-1.5"><Waveform size={14} weight="bold" /> Zone watchboard</h2>
                        {watchSum && (
                            <div className="flex items-center gap-1.5 flex-wrap">
                                {Object.keys(WATCH).map(k => (
                                    (watchSum.by_level?.[k] || 0) > 0 ? <span key={k} className={`chip ${WATCH[k].cls}`}>{watchSum.by_level[k]} {WATCH[k].label}</span> : null
                                ))}
                                {watchSum.stale_zones > 0 && (
                                    <span className="chip sev-unknown" title={`Older than ${watchSum.stale_after_hours}h`}><WarningCircle size={11} /> {watchSum.stale_zones} stale</span>
                                )}
                            </div>
                        )}
                        <button onClick={() => setOnlyActionable(v => !v)} data-testid="watch-filter" className={`chip ${onlyActionable ? "sev-high" : "sev-unknown"} hover:text-white ml-auto`}>
                            {onlyActionable ? "Showing actionable" : "Show all zones"}
                        </button>
                    </div>
                    <div className="tactical-card overflow-hidden" data-testid="watchboard">
                        <table className="w-full text-sm">
                            <thead className="border-b border-[var(--border)] font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">
                                <tr>
                                    <th className="text-left px-3 py-2">Zone</th>
                                    <th className="px-2 py-2">Watch</th>
                                    <th className="text-left px-2 py-2">What to do</th>
                                    <th className="px-2 py-2">Rain</th>
                                    <th className="px-2 py-2">Prob.</th>
                                    <th className="px-2 py-2">Age</th>
                                </tr>
                            </thead>
                            <tbody>
                                {watch.filter(w => !onlyActionable || w.watch_level === "WARNING" || w.watch_level === "WATCH").map(w => {
                                    const wl = WATCH[w.watch_level] || WATCH.STAND_DOWN;
                                    const arrow = TREND[w.trend] || "\u2013";
                                    return (
                                        <tr key={w.zone_id} className="border-b border-[var(--border)]" data-testid={`watch-${w.zone_id}`}>
                                            <td className="px-3 py-2">
                                                <div className="font-heading text-sm">{w.zone_name || w.zone_id}</div>
                                                <div className="font-mono text-[10px] text-[var(--text-2)]">{[w.district, w.state].filter(Boolean).join(", ") || "—"}</div>
                                            </td>
                                            <td className="px-2 py-2 text-center">
                                                <span className={`chip ${wl.cls}`}>{wl.label}</span>
                                                {w.escalated && <div className="font-mono text-[9px] text-[var(--sev-critical)] mt-0.5">escalated</div>}
                                            </td>
                                            <td className="px-2 py-2">
                                                <div className="text-[12px]">{w.cue}</div>
                                                <div className="font-mono text-[9px] text-[var(--text-2)] opacity-70">{(w.rationale || []).join(" · ")}</div>
                                            </td>
                                            <td className="px-2 py-2 text-center">
                                                <div className={`flex items-center justify-center gap-1 ${trendTone(w.trend)}`} title={w.trend_detail?.source || ""}>
                                                    <span className="font-mono text-[12px] leading-none">{arrow}</span>
                                                    <span className="font-mono text-[11px]">{w.trend === "UNKNOWN" ? "—" : w.trend.toLowerCase()}</span>
                                                </div>
                                                {w.trend_detail?.recent_3d_mm !== null && w.trend_detail?.recent_3d_mm !== undefined && (
                                                    <div className="font-mono text-[9px] text-[var(--text-2)]">{w.trend_detail.recent_3d_mm}mm / 3d</div>
                                                )}
                                            </td>
                                            <td className="px-2 py-2 text-center">
                                                <span className={`chip ${severityClass(w.severity)}`}>{w.probability !== null && w.probability !== undefined ? `${Math.round(w.probability * 100)}%` : "—"}</span>
                                            </td>
                                            <td className="px-2 py-2 text-center font-mono text-[11px]">
                                                <span className={w.stale ? "text-[var(--sev-medium)]" : "text-[var(--text-2)]"}>
                                                    {w.age_hours === null || w.age_hours === undefined ? "—" : `${w.age_hours}h`}
                                                </span>
                                                {w.stale && <div className="font-mono text-[9px] text-[var(--sev-medium)]">stale</div>}
                                            </td>
                                        </tr>
                                    );
                                })}
                                {!watch.length && <tr><td colSpan={6} className="text-center py-6 font-mono text-xs text-[var(--text-2)]">No predictions yet. Run a prediction to populate the watchboard.</td></tr>}
                            </tbody>
                        </table>
                        {watchSum && (
                            <div className="px-3 py-2 border-t border-[var(--border)] font-mono text-[9px] text-[var(--text-2)]">
                                {watchSum.zones_monitored} zones monitored · a prediction older than {watchSum.stale_after_hours}h is flagged stale · rainfall trend derived from stored prediction features
                            </div>
                        )}
                    </div>
                </section>

                <section>
                    <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5"><Pulse size={14} weight="bold" /> Live activity feed</h2>
                    <div className="tactical-card divide-y divide-[var(--border)]" data-testid="ops-feed">
                        {feed.map((e, i) => {
                            const k = KIND[e.kind] || { icon: FileText, label: e.kind, cls: "sev-unknown" };
                            const Icon = k.icon;
                            return (
                                <div key={`${e.ref_id}-${i}`} className="p-3 flex items-start gap-3" data-testid={`ops-evt-${i}`}>
                                    <div className="mt-0.5 text-[var(--text-2)]"><Icon size={16} /></div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className={`chip ${e.severity ? severityClass(e.severity) : k.cls}`}>{k.label}</span>
                                            <span className="font-heading text-sm truncate">{e.title}</span>
                                        </div>
                                        {e.detail ? <div className="font-mono text-[11px] text-[var(--text-2)] mt-0.5 truncate">{e.detail}</div> : null}
                                    </div>
                                    <div className="text-right shrink-0">
                                        <div className="font-mono text-[10px] text-[var(--text-2)]">{timeAgo(e.ts)}</div>
                                        <div className="font-mono text-[9px] text-[var(--text-2)] opacity-70">{e.source}</div>
                                    </div>
                                </div>
                            );
                        })}
                        {!feed.length && <div className="p-6 font-mono text-xs text-[var(--text-2)] text-center">No activity yet. Issue an alert or dispatch a team to populate the feed.</div>}
                    </div>
                </section>
            </div>
        </Shell>
    );
}
