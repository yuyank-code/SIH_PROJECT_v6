/**
 * Reports — the authority-side triage queue.
 *
 * The previous version of this page was a read-only table with two bugs that
 * made it actively misleading:
 *
 *   1. It rendered `r.timestamp`, but report rows carry `created_at`. Every row
 *      read "Invalid Date".
 *   2. It rendered `r.zone_id`, which the backend computed and then dropped on
 *      the floor instead of persisting — so the column showed "—" forever.
 *
 * Both are fixed at the source (see insert_report in supabase_repo.py). Beyond
 * that this is now a working queue rather than a log: an operator can see the
 * photo, see how many *other* people reported the same thing, and record a
 * decision. A citizen report that nobody can act on is just noise with a
 * timestamp.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Shell from "@/components/Shell";
// severityClass is deliberately not imported: a citizen report has a triage
// status, not a hazard severity, and borrowing the severity palette for it
// would make an unreviewed claim look like a graded risk assessment.
import { api } from "@/lib/api";
import {
    CheckCircle, XCircle, Camera, ArrowClockwise, Users, Warning, MapPin, Info,
} from "@phosphor-icons/react";

const STATUSES = ["SUBMITTED", "VERIFIED", "REJECTED", "DUPLICATE", "ACTIONED"];
const STATUS_CLASS = {
    SUBMITTED: "sev-medium", VERIFIED: "sev-low", ACTIONED: "sev-low",
    REJECTED: "sev-unknown", DUPLICATE: "sev-unknown",
};
const SIGNAL_CLASS = { CONFIRMED: "sev-low", CORROBORATED: "sev-medium", SINGLE: "sev-unknown" };

/** created_at, not timestamp — see the header comment. */
const when = (r) => {
    const raw = r.created_at;
    if (!raw) return "time not recorded";
    const d = new Date(raw);
    return Number.isNaN(d.getTime()) ? "time not recorded" : d.toLocaleString();
};

function Photos({ reportId }) {
    const [urls, setUrls] = useState(null);
    const [err, setErr] = useState("");
    useEffect(() => {
        let alive = true;
        // The report-media bucket is private, so the browser never gets the
        // service-role key — the server signs a short-lived URL and returns that.
        api.get(`/reports/${reportId}/media`)
            .then(({ data }) => { if (alive) setUrls(data); })
            .catch(() => { if (alive) setErr("Could not load evidence."); });
        return () => { alive = false; };
    }, [reportId]);

    if (err) return <div className="font-mono text-[10px] text-[var(--sev-high)]">{err}</div>;
    if (!urls) return <div className="font-mono text-[10px] text-[var(--text-2)]">Loading evidence…</div>;
    if (!urls.length) return <div className="font-mono text-[10px] text-[var(--text-2)]">No photo attached.</div>;

    return (
        <div className="flex gap-2 flex-wrap">
            {urls.map((m) => (m.url ? (
                <a key={m.id} href={m.url} target="_blank" rel="noreferrer" data-testid={`media-${m.id}`}>
                    <img src={m.url} alt="Report evidence" className="h-24 w-32 object-cover tactical-border hover:opacity-80" />
                </a>
            ) : (
                // A file we cannot sign is shown as a broken record, not hidden —
                // silently dropping it would understate the evidence on file.
                <div key={m.id} className="h-24 w-32 tactical-border flex items-center justify-center text-center font-mono text-[9px] text-[var(--text-2)] p-1">
                    File on record, link could not be generated
                </div>
            )))}
        </div>
    );
}

function ReportCard({ report, onTriage, busy }) {
    const [note, setNote] = useState(report.verification_note || "");
    const [open, setOpen] = useState(false);
    const corr = report.corroboration;

    return (
        <div className="tactical-card p-4 space-y-3" data-testid={`report-${report.id}`}>
            <div className="flex items-start gap-3 flex-wrap">
                <div className="flex-1 min-w-[12rem]">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-heading font-bold tracking-tight">{report.report_type?.replaceAll("_", " ")}</span>
                        <span className={`chip ${STATUS_CLASS[report.status] || "sev-unknown"}`}>{report.status}</span>
                        {report.media_count > 0 && <span className="chip sev-unknown"><Camera size={11} /> {report.media_count}</span>}
                        {corr && corr.signal !== "NONE" && (
                            <span className={`chip ${SIGNAL_CLASS[corr.signal] || "sev-unknown"}`} title={corr.label}>
                                <Users size={11} /> {corr.distinct_reporters} reporter{corr.distinct_reporters === 1 ? "" : "s"}
                            </span>
                        )}
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mt-1">
                        {when(report)} · {report.reporter_role || "CITIZEN"}
                    </div>
                </div>
                <div className="font-mono text-[11px] text-right text-[var(--text-2)]">
                    <div className="flex items-center gap-1 justify-end"><MapPin size={11} /> {report.lat?.toFixed(4)}, {report.lon?.toFixed(4)}</div>
                    {/* zone_name is null for rows written before nearest_zone_id was
                        persisted. Say that, rather than printing a bare dash that
                        looks like "no zone nearby". */}
                    <div>{report.zone_name || report.zone_id || "zone not resolved"}</div>
                </div>
            </div>

            {report.description && <p className="text-sm leading-relaxed">{report.description}</p>}

            <Photos reportId={report.id} />

            {corr && corr.signal !== "NONE" && (
                <div className="flex items-start gap-2 text-[11px] text-[var(--text-2)]">
                    <Info size={12} className="mt-[2px] shrink-0" />
                    <span>{corr.label} within {corr.radius_km} km in the last {corr.window_hours} h.</span>
                </div>
            )}

            {report.verification_note && (
                <div className="text-[11px] text-[var(--text-2)] border-l-2 border-[var(--border)] pl-2">
                    Note on file: {report.verification_note}
                </div>
            )}

            {!open ? (
                <button onClick={() => setOpen(true)} data-testid={`triage-open-${report.id}`} className="chip sev-medium">
                    Record a decision
                </button>
            ) : (
                <div className="space-y-2 border-t border-[var(--border)] pt-3">
                    <input
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder="What did you check, and what did you conclude?"
                        data-testid={`triage-note-${report.id}`}
                        className="w-full tactical-border bg-transparent px-2 py-2 text-xs font-body focus:outline-none focus:border-white"
                    />
                    <div className="flex gap-2 flex-wrap">
                        {STATUSES.filter((s) => s !== report.status).map((s) => (
                            <button
                                key={s}
                                disabled={busy}
                                onClick={() => onTriage(report.id, s, note)}
                                data-testid={`triage-${s}-${report.id}`}
                                className={`chip ${STATUS_CLASS[s]} disabled:opacity-40`}
                            >
                                {s === "VERIFIED" && <CheckCircle size={11} />}
                                {s === "REJECTED" && <XCircle size={11} />}
                                {s}
                            </button>
                        ))}
                        <button onClick={() => setOpen(false)} className="chip sev-unknown">Cancel</button>
                    </div>
                </div>
            )}
        </div>
    );
}

export default function Reports() {
    const [reports, setReports] = useState([]);
    const [summary, setSummary] = useState(null);
    const [status, setStatus] = useState("SUBMITTED");
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");

    const load = useCallback(async () => {
        setLoading(true); setErr("");
        try {
            const params = { limit: 200 };
            if (status !== "ALL") params.status = status;
            const [list, sum] = await Promise.all([
                api.get("/reports", { params }),
                api.get("/reports/summary"),
            ]);
            setReports(list.data);
            setSummary(sum.data);
        } catch (e) {
            setErr("Could not load reports.");
        } finally { setLoading(false); }
    }, [status]);

    useEffect(() => { load(); }, [load]);

    const triage = async (id, newStatus, note) => {
        setBusy(true);
        try {
            await api.patch(`/reports/${id}`, { status: newStatus, note });
            await load();
        } catch (e) {
            setErr("That decision could not be saved.");
        } finally { setBusy(false); }
    };

    const counts = summary?.by_status || {};
    const tabs = useMemo(() => ["SUBMITTED", "VERIFIED", "ACTIONED", "REJECTED", "DUPLICATE", "ALL"], []);

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="reports-page">
                <div className="flex items-end gap-4 flex-wrap">
                    <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Field / Citizen Reports</div>
                        <h1 className="font-heading text-3xl tracking-tighter font-bold">Report triage</h1>
                    </div>
                    <button onClick={load} disabled={loading} className="chip sev-low disabled:opacity-50 mb-1" data-testid="reports-refresh">
                        <ArrowClockwise size={11} /> {loading ? "Loading…" : "Refresh"}
                    </button>
                </div>

                {summary && (
                    <div className="tactical-card p-4 flex items-center gap-6 flex-wrap" data-testid="reports-summary">
                        <div>
                            <div className="font-heading text-2xl font-bold tracking-tighter">{summary.awaiting_triage}</div>
                            <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">Awaiting a decision</div>
                        </div>
                        <div>
                            <div className="font-heading text-2xl font-bold tracking-tighter">{summary.total}</div>
                            <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">Total on file</div>
                        </div>
                        <div>
                            <div className="font-heading text-2xl font-bold tracking-tighter">{summary.with_photo}</div>
                            <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">With photo evidence</div>
                        </div>
                        {summary.awaiting_triage > 0 && (
                            <div className="flex items-center gap-2 text-xs text-[var(--sev-medium)] ml-auto">
                                <Warning size={14} /> Unreviewed reports are not shown to the public.
                            </div>
                        )}
                    </div>
                )}

                <div className="flex gap-2 flex-wrap">
                    {tabs.map((t) => (
                        <button
                            key={t}
                            onClick={() => setStatus(t)}
                            data-testid={`filter-${t}`}
                            className={`chip ${status === t ? "sev-critical" : "sev-unknown"}`}
                        >
                            {t}{t !== "ALL" && counts[t] !== undefined ? ` (${counts[t]})` : ""}
                        </button>
                    ))}
                </div>

                {err && <div className="tactical-card p-3 text-xs text-[var(--sev-high)]" data-testid="reports-error">{err}</div>}

                <div className="space-y-3">
                    {reports.map((r) => <ReportCard key={r.id} report={r} onTriage={triage} busy={busy} />)}
                    {!loading && !reports.length && (
                        <div className="tactical-card p-8 text-center font-mono text-xs text-[var(--text-2)]" data-testid="reports-empty">
                            No reports with this status.
                        </div>
                    )}
                </div>
            </div>
        </Shell>
    );
}
