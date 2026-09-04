import { useEffect, useState, useCallback } from "react";
import Shell from "@/components/Shell";
import { api, severityClass, roleFromStorage } from "@/lib/api";
import { FirstAid, Package, Plus, MapPin, Users, CheckCircle, FileText, X, ArrowClockwise, ArrowRight } from "@phosphor-icons/react";

// Feature D — Post-landslide mitigation & recovery.
// Incidents (confirmed events) -> per-village impact/needs assessment + relief
// resource tracking + recovery tasks. Authority confirms incidents and manages
// resources; field officers file impact assessments. Every write carries a
// source server-side (no fabricated data). Backend enforces the role split;
// this UI simply surfaces the forms.
//
// v4 adds the Recovery Playbook: a phased, NDMA/Sphere-aligned checklist
// (relief -> early recovery -> restoration -> resilience) generated per
// confirmed incident, with per-phase and overall progress, plus a one-click
// SITREP (situation report) composed from data already on the incident.
// Each step also carries guidance — `manageable_when` (the condition that makes
// it actionable) and `requires_assessment` (must be confirmed on the ground
// before it can be closed) — and a cross-incident overview table shows which
// phase every recovery is in, from GET /recovery/overview.
const INC_STATUS = ["ACTIVE", "CONTAINED", "CLOSED"];
const IMPACT_STATUS = ["ASSESSING", "PARTIAL", "ASSESSED"];
const RES_TYPES = ["SHELTER", "FOOD", "WATER", "MEDICAL", "RESCUE_TEAM", "LOGISTICS", "OTHER"];
const RES_STATUS = ["REQUESTED", "ALLOCATED", "IN_TRANSIT", "DELIVERED"];
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const STEP_STATES = ["PENDING", "IN_PROGRESS", "DONE", "NA"];
const PLAYBOOK_PHASES = ["RELIEF", "EARLY_RECOVERY", "RESTORATION", "RESILIENCE"];

const stepChip = (s) => ({ PENDING: "sev-unknown", IN_PROGRESS: "sev-medium", DONE: "sev-low", NA: "sev-unknown" }[s] || "sev-unknown");
const phaseTone = (p) => ({ RELIEF: "sev-critical", EARLY_RECOVERY: "sev-high", RESTORATION: "sev-medium", RESILIENCE: "sev-low" }[p] || "sev-unknown");

const statusChip = (s) => ({
    ACTIVE: "sev-critical", CONTAINED: "sev-medium", CLOSED: "sev-low",
    ASSESSING: "sev-medium", PARTIAL: "sev-high", ASSESSED: "sev-low",
    REQUESTED: "sev-medium", ALLOCATED: "sev-high", IN_TRANSIT: "sev-high", DELIVERED: "sev-low",
}[s] || "sev-unknown");

const num = (v) => (v === null || v === undefined || v === "") ? "—" : v;

export default function Recovery() {
    const [incidents, setIncidents] = useState([]);
    const [zones, setZones] = useState([]);
    const [selId, setSelId] = useState(null);
    const [detail, setDetail] = useState(null);
    const [showNew, setShowNew] = useState(false);
    const [incForm, setIncForm] = useState({ zone_id: "", title: "", severity: "HIGH", summary: "" });
    const [impForm, setImpForm] = useState({ village_name: "", affected_population: "", households: "", casualties: "", injured: "", notes: "" });
    const [resForm, setResForm] = useState({ resource_type: "SHELTER", label: "", quantity: "", unit: "", notes: "" });
    const [busy, setBusy] = useState(false);
    const [genBusy, setGenBusy] = useState(false);
    const [stepForm, setStepForm] = useState({ phase: "EARLY_RECOVERY", title: "", detail: "", requires_assessment: false });
    const [showStepForm, setShowStepForm] = useState(false);
    const [sitrep, setSitrep] = useState(null);
    const [copied, setCopied] = useState(false);
    const [overview, setOverview] = useState([]);
    const [showOverview, setShowOverview] = useState(true);

    // Header counters for the overview — derived, so they always match the table.
    const overviewStats = {
        planned: overview.filter(o => o.plan).length,
        awaiting: overview.reduce((n, o) => n + (o.plan?.awaiting_assessment || 0), 0),
    };

    const role = roleFromStorage();
    const canManage = ["ADMIN", "AUTHORITY", "FIELD_OFFICER"].includes(role);
    const canGenerate = ["ADMIN", "AUTHORITY"].includes(role);

    const loadList = useCallback(async () => {
        const r = await api.get("/incidents");
        setIncidents(r.data);
        if (!selId && r.data.length) setSelId(r.data[0].id);
    }, [selId]);

    // Cross-incident recovery status. Server-side aggregate of the same plans
    // shown on the detail page, so the numbers can never disagree.
    const loadOverview = useCallback(async () => {
        const r = await api.get("/recovery/overview");
        setOverview(r.data);
    }, []);

    const loadDetail = useCallback(async (id) => {
        if (!id) return;
        const r = await api.get(`/incidents/${id}`);
        setDetail(r.data);
    }, []);

    useEffect(() => { loadList(); loadOverview(); api.get("/zones").then(r => setZones(r.data)); }, [loadList, loadOverview]);
    useEffect(() => { loadDetail(selId); setSitrep(null); setCopied(false); setShowStepForm(false); setStepForm({ phase: "EARLY_RECOVERY", title: "", detail: "", requires_assessment: false }); }, [selId, loadDetail]);

    // ---- Recovery Playbook (v4) -------------------------------------------
    // The plan is embedded in GET /incidents/{id} as `recovery_plan`, so every
    // mutation just reloads the detail — one source of truth, no local drift.
    const generatePlan = async () => {
        setGenBusy(true);
        try {
            await api.post(`/incidents/${selId}/recovery-plan`);
            await Promise.all([loadDetail(selId), loadOverview()]);
        } finally { setGenBusy(false); }
    };

    const cycleStep = async (st) => {
        const next = STEP_STATES[(STEP_STATES.indexOf(st.status) + 1) % STEP_STATES.length];
        await api.patch(`/recovery-steps/${st.id}`, { status: next });
        await Promise.all([loadDetail(selId), loadOverview()]);
    };

    const addStep = async () => {
        if (!stepForm.title || !detail?.recovery_plan?.id) return;
        setBusy(true);
        try {
            await api.post(`/recovery-plans/${detail.recovery_plan.id}/steps`, stepForm);
            setStepForm({ phase: "EARLY_RECOVERY", title: "", detail: "", requires_assessment: false });
            setShowStepForm(false);
            await Promise.all([loadDetail(selId), loadOverview()]);
        } finally { setBusy(false); }
    };

    // ---- SITREP (v4) -------------------------------------------------------
    const loadSitrep = async () => {
        const r = await api.get(`/incidents/${selId}/sitrep`);
        setSitrep(r.data);
        setCopied(false);
    };

    const copySitrep = async () => {
        if (!sitrep?.markdown) return;
        try {
            await navigator.clipboard.writeText(sitrep.markdown);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch (e) { /* clipboard blocked — the text is on screen to copy manually */ }
    };

    const intInput = (v) => v === "" ? null : parseInt(v, 10);

    const createIncident = async () => {
        if (!incForm.title || !incForm.zone_id) return;
        setBusy(true);
        try {
            const r = await api.post("/incidents", incForm);
            setIncForm({ zone_id: "", title: "", severity: "HIGH", summary: "" });
            setShowNew(false);
            await Promise.all([loadList(), loadOverview()]);
            setSelId(r.data.id);
        } finally { setBusy(false); }
    };

    const setIncidentStatus = async (status) => {
        await api.patch(`/incidents/${selId}`, { status });
        await Promise.all([loadList(), loadDetail(selId), loadOverview()]);
    };

    const addImpact = async () => {
        if (!impForm.village_name) return;
        setBusy(true);
        try {
            await api.post(`/incidents/${selId}/impacts`, {
                village_name: impForm.village_name,
                affected_population: intInput(impForm.affected_population),
                households: intInput(impForm.households),
                casualties: intInput(impForm.casualties),
                injured: intInput(impForm.injured),
                notes: impForm.notes,
            });
            setImpForm({ village_name: "", affected_population: "", households: "", casualties: "", injured: "", notes: "" });
            await loadDetail(selId);
        } finally { setBusy(false); }
    };

    const cycleImpact = async (imp) => {
        const next = IMPACT_STATUS[(IMPACT_STATUS.indexOf(imp.status) + 1) % IMPACT_STATUS.length];
        await api.patch(`/impacts/${imp.id}`, { status: next });
        await loadDetail(selId);
    };

    const addResource = async () => {
        setBusy(true);
        try {
            await api.post(`/incidents/${selId}/resources`, {
                resource_type: resForm.resource_type,
                label: resForm.label || null,
                quantity: resForm.quantity === "" ? null : parseFloat(resForm.quantity),
                unit: resForm.unit || null,
                notes: resForm.notes,
            });
            setResForm({ resource_type: "SHELTER", label: "", quantity: "", unit: "", notes: "" });
            await loadDetail(selId);
        } finally { setBusy(false); }
    };

    const advanceResource = async (res) => {
        const next = RES_STATUS[(RES_STATUS.indexOf(res.status) + 1) % RES_STATUS.length];
        await api.patch(`/resources/${res.id}`, { status: next });
        await loadDetail(selId);
    };

    const inputCls = "w-full tactical-border bg-transparent px-2 py-1.5 text-sm focus:outline-none focus:border-white";

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="recovery-page">
                <div className="flex items-center gap-3 flex-wrap">
                    <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Mitigation &amp; recovery</div>
                        <h1 className="font-heading text-3xl tracking-tighter font-bold">After the landslide</h1>
                    </div>
                    <button onClick={() => setShowNew(v => !v)} data-testid="new-incident-toggle" className="ml-auto chip sev-critical hover:bg-red-500"><Plus size={12} /> Confirm incident</button>
                </div>

                {showNew && (
                    <div className="tactical-card p-4 space-y-2" data-testid="new-incident-form">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">Authority only · records a confirmed event</div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            <select value={incForm.zone_id} onChange={e => setIncForm({ ...incForm, zone_id: e.target.value })} data-testid="inc-zone" className={inputCls}>
                                <option value="">Select zone…</option>
                                {zones.map(z => <option key={z.zone_id} value={z.zone_id}>{z.zone_id} — {z.name}</option>)}
                            </select>
                            <select value={incForm.severity} onChange={e => setIncForm({ ...incForm, severity: e.target.value })} data-testid="inc-severity" className={inputCls}>
                                {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
                            </select>
                        </div>
                        <input placeholder="Title (e.g. NH-44 slope failure near Sonapur)" value={incForm.title} onChange={e => setIncForm({ ...incForm, title: e.target.value })} data-testid="inc-title" className={inputCls} />
                        <textarea placeholder="Summary" value={incForm.summary} onChange={e => setIncForm({ ...incForm, summary: e.target.value })} data-testid="inc-summary" className={inputCls} rows={2} />
                        <button onClick={createIncident} disabled={busy} data-testid="inc-save" className="w-full py-2 bg-[var(--sev-critical)] text-white text-xs font-mono uppercase tracking-[0.15em] hover:bg-red-500 disabled:opacity-50">{busy ? "Saving…" : "Confirm incident"}</button>
                    </div>
                )}

                <section>
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold flex items-center gap-1.5"><CheckCircle size={14} /> Recovery status across incidents</h2>
                        {overviewStats.planned > 0 && (
                            <span className="font-mono text-[10px] text-[var(--text-2)]">{overviewStats.planned} with a plan · {overviewStats.awaiting} step(s) awaiting field check</span>
                        )}
                        <button onClick={() => setShowOverview(v => !v)} data-testid="overview-toggle" className="chip sev-unknown hover:text-white ml-auto">{showOverview ? "Hide" : "Show"}</button>
                    </div>
                    {showOverview && (
                        <div className="tactical-card overflow-hidden" data-testid="recovery-overview">
                            <table className="w-full text-sm">
                                <thead className="border-b border-[var(--border)] font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">
                                    <tr>
                                        <th className="text-left px-3 py-2">Incident</th>
                                        <th className="px-2 py-2">Now in</th>
                                        <th className="text-left px-2 py-2">Progress</th>
                                        <th className="px-2 py-2">Field check</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {overview.map(o => (
                                        <tr key={o.incident_id} onClick={() => setSelId(o.incident_id)} data-testid={`ov-${o.incident_id}`}
                                            className={`border-b border-[var(--border)] cursor-pointer hover:bg-white/[0.03] ${selId === o.incident_id ? "bg-white/5" : ""}`}>
                                            <td className="px-3 py-2">
                                                <div className="flex items-center gap-1.5 flex-wrap">
                                                    <span className={`chip ${statusChip(o.status)}`}>{o.status}</span>
                                                    {o.severity && <span className={`chip ${severityClass(o.severity)}`}>{o.severity}</span>}
                                                    <span className="font-heading text-sm truncate">{o.title}</span>
                                                </div>
                                                <div className="font-mono text-[9px] text-[var(--text-2)] mt-0.5">{[o.zone_name || o.zone_code, o.district].filter(Boolean).join(", ") || "—"}</div>
                                            </td>
                                            <td className="px-2 py-2 text-center">
                                                {!o.plan ? <span className="font-mono text-[10px] text-[var(--text-2)]">no plan</span>
                                                    : o.plan.current_phase ? <span className={`chip ${phaseTone(o.plan.current_phase.phase)}`}>{o.plan.current_phase.label}</span>
                                                        : <span className="chip sev-low">All phases done</span>}
                                            </td>
                                            <td className="px-2 py-2">
                                                {!o.plan ? (
                                                    <span className="font-mono text-[10px] text-[var(--text-2)]">— not started</span>
                                                ) : (
                                                    <>
                                                        <div className="h-1.5 w-full bg-white/10">
                                                            <div className="h-full bg-[var(--sev-low)]" style={{ width: `${o.plan.progress?.overall_pct || 0}%` }} />
                                                        </div>
                                                        <div className="font-mono text-[9px] text-[var(--text-2)] mt-0.5">
                                                            {o.plan.progress?.overall_done}/{o.plan.progress?.overall_total} steps · {o.plan.progress?.overall_pct}%{o.plan.in_progress ? ` · ${o.plan.in_progress} running` : ""}
                                                        </div>
                                                    </>
                                                )}
                                            </td>
                                            <td className="px-2 py-2 text-center font-mono text-[11px]">
                                                {!o.plan ? "—" : o.plan.awaiting_assessment
                                                    ? <span className="chip sev-medium">{o.plan.awaiting_assessment} pending</span>
                                                    : <span className="text-[var(--text-2)]">clear</span>}
                                            </td>
                                        </tr>
                                    ))}
                                    {!overview.length && <tr><td colSpan={4} className="text-center py-6 font-mono text-xs text-[var(--text-2)]">No incidents yet — nothing to recover from.</td></tr>}
                                </tbody>
                            </table>
                            <div className="px-3 py-2 border-t border-[var(--border)] font-mono text-[9px] text-[var(--text-2)]">
                                "Field check" counts steps that must be confirmed on the ground before they can be closed. An incident with no plan shows "not started" — never a fabricated 0%.
                            </div>
                        </div>
                    )}
                </section>

                <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
                    <section>
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2">Incidents ({incidents.length})</h2>
                        <div className="tactical-card divide-y divide-[var(--border)]" data-testid="incident-list">
                            {incidents.map(i => (
                                <button key={i.id} onClick={() => setSelId(i.id)} data-testid={`inc-${i.id}`} className={`w-full text-left p-3 hover:bg-white/[0.03] ${selId === i.id ? "bg-white/5 border-l-2 border-[var(--sev-critical)]" : "border-l-2 border-transparent"}`}>
                                    <div className="flex items-center gap-2"><span className={`chip ${statusChip(i.status)}`}>{i.status}</span>{i.severity && <span className={`chip ${severityClass(i.severity)}`}>{i.severity}</span>}</div>
                                    <div className="font-heading text-sm mt-1 truncate">{i.title}</div>
                                    <div className="font-mono text-[10px] text-[var(--text-2)] flex items-center gap-1"><MapPin size={10} />{i.zone_name || i.zone_code || "—"}{i.district ? `, ${i.district}` : ""}</div>
                                    <div className="font-mono text-[9px] text-[var(--text-2)] mt-0.5">{i.occurred_at ? new Date(i.occurred_at).toLocaleString() : ""}</div>
                                </button>
                            ))}
                            {!incidents.length && <div className="p-6 font-mono text-xs text-[var(--text-2)] text-center">No incidents yet. Confirm one when an event is verified in the field.</div>}
                        </div>
                    </section>

                    <section className="space-y-4">
                        {!detail ? (
                            <div className="tactical-card p-6 font-mono text-xs text-[var(--text-2)] text-center" data-testid="no-selection">Select an incident to see impact &amp; relief.</div>
                        ) : (
                            <>
                                <div className="tactical-card p-4" data-testid="incident-detail">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className={`chip ${statusChip(detail.status)}`}>{detail.status}</span>
                                        {detail.severity && <span className={`chip ${severityClass(detail.severity)}`}>{detail.severity}</span>}
                                        <span className="font-mono text-[10px] text-[var(--text-2)]">{detail.zone_name || detail.zone_code} · src {detail.source}</span>
                                    </div>
                                    <h3 className="font-heading text-xl mt-1">{detail.title}</h3>
                                    {detail.summary ? <p className="text-sm text-[var(--text-2)] mt-1">{detail.summary}</p> : null}
                                    <div className="flex items-center gap-1.5 mt-2">
                                        <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-[var(--text-2)] mr-1">Set status:</span>
                                        {INC_STATUS.map(s => (
                                            <button key={s} onClick={() => setIncidentStatus(s)} disabled={detail.status === s} data-testid={`set-${s}`} className={`chip ${detail.status === s ? statusChip(s) : "sev-unknown"} disabled:opacity-100 hover:text-white`}>{s}</button>
                                        ))}
                                        <button onClick={loadSitrep} data-testid="sitrep-btn" className="chip sev-unknown hover:text-white ml-auto"><FileText size={12} /> SITREP</button>
                                    </div>
                                </div>

                                {sitrep && (
                                    <div className="tactical-card p-4" data-testid="sitrep-panel">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <FileText size={14} />
                                            <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold">Situation report</h2>
                                            <span className="font-mono text-[9px] text-[var(--text-2)]">generated {sitrep.generated_at ? new Date(sitrep.generated_at).toLocaleString() : "—"}</span>
                                            <div className="ml-auto flex items-center gap-1.5">
                                                <button onClick={copySitrep} data-testid="sitrep-copy" className="chip sev-low hover:text-white">{copied ? "Copied" : "Copy"}</button>
                                                <button onClick={() => setSitrep(null)} data-testid="sitrep-close" className="chip sev-unknown hover:text-white"><X size={12} /></button>
                                            </div>
                                        </div>
                                        <p className="font-mono text-[10px] text-[var(--text-2)] mt-1">Composed from this incident's own records. Blank figures mean "not assessed" — never reported as zero.</p>
                                        <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-[var(--text-2)] tactical-border p-3" data-testid="sitrep-text">{sitrep.markdown}</pre>
                                    </div>
                                )}

                                <div>
                                    <div className="flex items-center gap-2 flex-wrap mb-2">
                                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold flex items-center gap-1.5"><CheckCircle size={14} /> Recovery playbook</h2>
                                        {detail.recovery_plan?.progress ? (
                                            <span className="font-mono text-[10px] text-[var(--text-2)]">{detail.recovery_plan.progress.overall_done}/{detail.recovery_plan.progress.overall_total} steps · {detail.recovery_plan.progress.overall_pct}%</span>
                                        ) : null}
                                        <div className="ml-auto flex items-center gap-1.5">
                                            {detail.recovery_plan && canManage && (
                                                <button onClick={() => setShowStepForm(v => !v)} data-testid="step-form-toggle" className="chip sev-unknown hover:text-white"><Plus size={12} /> Add step</button>
                                            )}
                                            {canGenerate && (
                                                <button onClick={generatePlan} disabled={genBusy} data-testid="gen-plan" className="chip sev-high hover:text-white disabled:opacity-50">
                                                    {detail.recovery_plan ? <><ArrowClockwise size={12} /> {genBusy ? "Syncing…" : "Sync steps"}</> : <><Plus size={12} /> {genBusy ? "Generating…" : "Generate plan"}</>}
                                                </button>
                                            )}
                                        </div>
                                    </div>

                                    {!detail.recovery_plan ? (
                                        <div className="tactical-card p-6 text-center" data-testid="no-plan">
                                            <div className="font-heading text-sm">No recovery plan yet</div>
                                            <p className="font-mono text-[11px] text-[var(--text-2)] mt-1 max-w-lg mx-auto">
                                                Generate one to get the standard phased checklist — immediate relief, early recovery, restoration, and long-term resilience — scaled to this incident's severity. It is guidance, not a record of work done: every step starts PENDING.
                                            </p>
                                            {!canGenerate && <p className="font-mono text-[10px] text-[var(--text-2)] mt-2">Authority sign-in required to generate.</p>}
                                        </div>
                                    ) : (
                                        <div className="space-y-3" data-testid="recovery-plan">
                                            <div className="tactical-card p-3">
                                                <div className="flex items-center justify-between gap-2 flex-wrap">
                                                    <span className="font-mono text-[10px] text-[var(--text-2)]">{detail.recovery_plan.framework}</span>
                                                    <span className={`chip ${detail.recovery_plan.status === "COMPLETE" ? "sev-low" : "sev-medium"}`}>{detail.recovery_plan.status}</span>
                                                </div>
                                                <div className="mt-2 h-1.5 w-full bg-white/10" data-testid="overall-bar">
                                                    <div className="h-full bg-[var(--sev-low)]" style={{ width: `${detail.recovery_plan.progress?.overall_pct || 0}%` }} />
                                                </div>
                                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
                                                    {(detail.recovery_plan.progress?.phases || []).map(ph => (
                                                        <div key={ph.phase} data-testid={`phase-stat-${ph.phase}`}>
                                                            <div className="flex items-center gap-1.5">
                                                                <span className={`chip ${phaseTone(ph.phase)}`}>{ph.pct}%</span>
                                                                <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-[var(--text-2)] truncate">{ph.label}</span>
                                                            </div>
                                                            <div className="font-mono text-[9px] text-[var(--text-2)] mt-0.5">{ph.done}/{ph.total} done{ph.na ? ` · ${ph.na} n/a` : ""}</div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>

                                            {showStepForm && (
                                                <div className="tactical-card p-3 space-y-2" data-testid="step-form">
                                                    <div className="grid grid-cols-1 md:grid-cols-[160px_1fr_auto] gap-2 items-center">
                                                        <select value={stepForm.phase} onChange={e => setStepForm({ ...stepForm, phase: e.target.value })} className={inputCls} data-testid="step-phase">
                                                            {PLAYBOOK_PHASES.map(p => <option key={p} value={p}>{p.replace("_", " ")}</option>)}
                                                        </select>
                                                        <input placeholder="Step to add for this event" value={stepForm.title} onChange={e => setStepForm({ ...stepForm, title: e.target.value })} className={inputCls} data-testid="step-title" />
                                                        <button onClick={addStep} disabled={busy} data-testid="step-add" className="py-1.5 px-4 bg-[var(--sev-critical)] text-white text-[11px] font-mono uppercase tracking-[0.1em] hover:bg-red-500 disabled:opacity-50">Add</button>
                                                    </div>
                                                    <label className="flex items-center gap-2 font-mono text-[10px] text-[var(--text-2)] cursor-pointer">
                                                        <input type="checkbox" checked={stepForm.requires_assessment} onChange={e => setStepForm({ ...stepForm, requires_assessment: e.target.checked })} data-testid="step-assess" />
                                                        Needs on-ground confirmation before it can be marked done
                                                    </label>
                                                </div>
                                            )}

                                            {(detail.recovery_plan.progress?.phases || []).map(ph => {
                                                const steps = (detail.recovery_plan.steps || []).filter(s => s.phase === ph.phase);
                                                if (!steps.length) return null;
                                                return (
                                                    <div key={ph.phase} className="tactical-card overflow-hidden" data-testid={`phase-${ph.phase}`}>
                                                        <div className="px-3 py-2 border-b border-[var(--border)] flex items-center gap-2 flex-wrap">
                                                            <span className={`chip ${phaseTone(ph.phase)}`}>{ph.label}</span>
                                                            <span className="font-mono text-[10px] text-[var(--text-2)]">{ph.window}</span>
                                                            <span className="ml-auto font-mono text-[10px] text-[var(--text-2)]">{ph.done}/{ph.total}</span>
                                                        </div>
                                                        <div className="divide-y divide-[var(--border)]">
                                                            {steps.map(st => (
                                                                <div key={st.id} className={`p-3 flex items-start gap-3 ${st.status === "NA" ? "opacity-50" : ""}`} data-testid={`step-${st.id}`}>
                                                                    <div className="flex-1 min-w-0">
                                                                        <div className="flex items-center gap-2 flex-wrap">
                                                                            <span className={`font-heading text-sm ${st.status === "DONE" ? "line-through text-[var(--text-2)]" : ""}`}>{st.title}</span>
                                                                            {st.source === "MANUAL" && <span className="chip sev-unknown font-mono text-[9px]">added</span>}
                                                                        </div>
                                                                        {st.detail ? <div className="font-mono text-[10px] text-[var(--text-2)] mt-0.5">{st.detail}</div> : null}
                                                                        {(st.manageable_when || st.requires_assessment) && (
                                                                            <div className="flex items-center gap-1.5 flex-wrap mt-1">
                                                                                {st.manageable_when ? <span className="chip sev-unknown font-mono text-[9px]">when: {st.manageable_when}</span> : null}
                                                                                {st.requires_assessment ? <span className="chip sev-medium font-mono text-[9px]" title="Confirm on the ground before marking done — never from a desk">needs on-ground check</span> : null}
                                                                            </div>
                                                                        )}
                                                                        <div className="font-mono text-[9px] text-[var(--text-2)] opacity-70 mt-0.5">
                                                                            {st.code}{st.owner ? ` · ${st.owner}` : ""}{st.done_at ? ` · done ${new Date(st.done_at).toLocaleDateString()}` : ""}
                                                                        </div>
                                                                    </div>
                                                                    <button onClick={() => cycleStep(st)} disabled={!canManage} data-testid={`step-status-${st.id}`} className={`chip ${stepChip(st.status)} hover:text-white disabled:opacity-60 shrink-0`}>
                                                                        {st.status}{canManage ? <ArrowRight size={10} /> : null}
                                                                    </button>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>

                                <div>
                                    <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5"><Users size={14} /> Per-village impact ({detail.impacts?.length || 0})</h2>
                                    <div className="tactical-card overflow-hidden" data-testid="impact-table">
                                        <table className="w-full text-sm">
                                            <thead className="border-b border-[var(--border)] font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">
                                                <tr><th className="text-left px-3 py-2">Village</th><th className="px-2 py-2">Affected</th><th className="px-2 py-2">Homes</th><th className="px-2 py-2">Cas.</th><th className="px-2 py-2">Inj.</th><th className="px-2 py-2">Status</th></tr>
                                            </thead>
                                            <tbody>
                                                {(detail.impacts || []).map(im => (
                                                    <tr key={im.id} className="border-b border-[var(--border)]" data-testid={`impact-${im.id}`}>
                                                        <td className="px-3 py-2"><div className="font-heading text-sm">{im.village_name || "—"}</div>{im.notes ? <div className="font-mono text-[10px] text-[var(--text-2)] truncate max-w-[16rem]">{im.notes}</div> : null}</td>
                                                        <td className="px-2 py-2 text-center font-mono text-[12px]">{num(im.affected_population)}</td>
                                                        <td className="px-2 py-2 text-center font-mono text-[12px]">{num(im.households)}</td>
                                                        <td className="px-2 py-2 text-center font-mono text-[12px] text-[var(--sev-critical)]">{num(im.casualties)}</td>
                                                        <td className="px-2 py-2 text-center font-mono text-[12px] text-[var(--sev-high)]">{num(im.injured)}</td>
                                                        <td className="px-2 py-2 text-center"><button onClick={() => cycleImpact(im)} data-testid={`impact-status-${im.id}`} className={`chip ${statusChip(im.status)} hover:text-white`}>{im.status}</button></td>
                                                    </tr>
                                                ))}
                                                {!(detail.impacts || []).length && <tr><td colSpan={6} className="text-center py-4 font-mono text-xs text-[var(--text-2)]">No assessments filed. Blank counts mean "not assessed", not zero.</td></tr>}
                                            </tbody>
                                        </table>
                                        <div className="p-3 border-t border-[var(--border)] grid grid-cols-2 md:grid-cols-6 gap-2 items-center" data-testid="impact-form">
                                            <input placeholder="Village" value={impForm.village_name} onChange={e => setImpForm({ ...impForm, village_name: e.target.value })} className={inputCls + " col-span-2"} data-testid="imp-village" />
                                            <input placeholder="Affected" inputMode="numeric" value={impForm.affected_population} onChange={e => setImpForm({ ...impForm, affected_population: e.target.value })} className={inputCls} data-testid="imp-affected" />
                                            <input placeholder="Homes" inputMode="numeric" value={impForm.households} onChange={e => setImpForm({ ...impForm, households: e.target.value })} className={inputCls} />
                                            <input placeholder="Cas." inputMode="numeric" value={impForm.casualties} onChange={e => setImpForm({ ...impForm, casualties: e.target.value })} className={inputCls} />
                                            <input placeholder="Inj." inputMode="numeric" value={impForm.injured} onChange={e => setImpForm({ ...impForm, injured: e.target.value })} className={inputCls} />
                                            <input placeholder="Notes (optional)" value={impForm.notes} onChange={e => setImpForm({ ...impForm, notes: e.target.value })} className={inputCls + " col-span-2 md:col-span-5"} />
                                            <button onClick={addImpact} disabled={busy} data-testid="imp-add" className="py-1.5 bg-[var(--sev-critical)] text-white text-[11px] font-mono uppercase tracking-[0.1em] hover:bg-red-500 disabled:opacity-50">Add</button>
                                        </div>
                                    </div>
                                </div>

                                <div>
                                    <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5"><Package size={14} /> Relief resources ({detail.resources?.length || 0})</h2>
                                    <div className="tactical-card divide-y divide-[var(--border)]" data-testid="resource-list">
                                        {(detail.resources || []).map(r => (
                                            <div key={r.id} className="p-3 flex items-center gap-2" data-testid={`res-${r.id}`}>
                                                <span className="chip sev-unknown font-mono text-[10px]">{r.resource_type}</span>
                                                <div className="flex-1 min-w-0"><div className="font-heading text-sm truncate">{r.label || r.resource_type}</div>{r.notes ? <div className="font-mono text-[10px] text-[var(--text-2)] truncate">{r.notes}</div> : null}</div>
                                                {(r.quantity !== null && r.quantity !== undefined) && <span className="font-mono text-[11px] text-[var(--text-2)]">{r.quantity} {r.unit || ""}</span>}
                                                <button onClick={() => advanceResource(r)} data-testid={`res-status-${r.id}`} className={`chip ${statusChip(r.status)} hover:text-white`}>{r.status} →</button>
                                            </div>
                                        ))}
                                        {!(detail.resources || []).length && <div className="p-4 font-mono text-xs text-[var(--text-2)] text-center">No resources logged yet.</div>}
                                        <div className="p-3 grid grid-cols-2 md:grid-cols-6 gap-2 items-center" data-testid="resource-form">
                                            <select value={resForm.resource_type} onChange={e => setResForm({ ...resForm, resource_type: e.target.value })} className={inputCls} data-testid="res-type">
                                                {RES_TYPES.map(x => <option key={x} value={x}>{x}</option>)}
                                            </select>
                                            <input placeholder="Label" value={resForm.label} onChange={e => setResForm({ ...resForm, label: e.target.value })} className={inputCls + " col-span-2"} data-testid="res-label" />
                                            <input placeholder="Qty" inputMode="decimal" value={resForm.quantity} onChange={e => setResForm({ ...resForm, quantity: e.target.value })} className={inputCls} />
                                            <input placeholder="Unit" value={resForm.unit} onChange={e => setResForm({ ...resForm, unit: e.target.value })} className={inputCls} />
                                            <button onClick={addResource} disabled={busy} data-testid="res-add" className="py-1.5 bg-[var(--sev-critical)] text-white text-[11px] font-mono uppercase tracking-[0.1em] hover:bg-red-500 disabled:opacity-50">Add</button>
                                        </div>
                                    </div>
                                </div>

                                {detail.recovery_tasks?.length ? (
                                    <div>
                                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5"><FirstAid size={14} /> Linked tasks ({detail.recovery_tasks.length})</h2>
                                        <div className="tactical-card divide-y divide-[var(--border)]" data-testid="linked-tasks">
                                            {detail.recovery_tasks.map(tk => (
                                                <div key={tk.id} className="p-3 flex items-center gap-2">
                                                    <span className="chip sev-unknown">{tk.phase}</span>
                                                    <span className="font-heading text-sm flex-1 truncate">{tk.title}</span>
                                                    <span className={`chip ${statusChip(tk.status)}`}>{tk.status}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ) : null}
                            </>
                        )}
                    </section>
                </div>
            </div>
        </Shell>
    );
}
