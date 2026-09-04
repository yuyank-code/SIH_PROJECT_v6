import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";
import { Brain, Target, Warning, ChartBar, ShieldCheck, Info } from "@phosphor-icons/react";

// Feature C — Model transparency panel.
// Read-only "what this model does and does NOT do" view. Every value is served
// by GET /model/transparency, which reads the shipped model artifacts — nothing
// is fabricated on the frontend.
export default function ModelCard() {
    const [t, setT] = useState(null);
    const [err, setErr] = useState(null);
    useEffect(() => {
        api.get("/model/transparency").then(r => setT(r.data)).catch(e => setErr(e?.message || "failed to load"));
    }, []);

    if (err) return <Shell><div className="p-6 font-mono text-xs text-[var(--sev-critical)]" data-testid="model-error">Could not load model card: {err}</div></Shell>;
    if (!t) return <Shell><div className="p-6 font-mono text-xs text-[var(--text-2)]" data-testid="model-loading">Loading model card…</div></Shell>;

    const importances = Object.entries(t.global_importance || {}).sort((a, b) => b[1] - a[1]);
    const maxImp = importances.length ? Math.max(...importances.map(([, v]) => v)) : 1;

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="model-card-page">
                <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Model transparency</div>
                    <h1 className="font-heading text-3xl tracking-tighter font-bold">What the model predicts</h1>
                    <p className="text-sm text-[var(--text-2)] mt-1 max-w-2xl">{t.task}</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="tactical-card p-4" data-testid="mc-version">
                        <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]"><Brain size={13} /> Algorithm</div>
                        <div className="font-heading text-lg mt-1">{t.algorithm}</div>
                        <div className="font-mono text-[11px] text-[var(--text-2)] mt-1">version <span className="text-white">{t.version}</span> · {t.feature_count} features</div>
                    </div>
                    <div className="tactical-card p-4" data-testid="mc-threshold">
                        <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]"><Target size={13} /> Operating threshold</div>
                        <div className="font-heading text-lg mt-1">{t.operating_threshold?.value}</div>
                        <div className="font-mono text-[11px] text-[var(--text-2)] mt-1">{t.operating_threshold?.chosen_for}</div>
                        <div className="font-mono text-[9px] text-[var(--text-2)] mt-1">src: {t.operating_threshold?.source}</div>
                    </div>
                    <div className="tactical-card p-4" data-testid="mc-calibration">
                        <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]"><ShieldCheck size={13} /> Prior correction</div>
                        <div className="font-heading text-lg mt-1">{t.calibration?.enabled ? "ENABLED" : "OFF"}</div>
                        <div className="font-mono text-[11px] text-[var(--text-2)] mt-1">
                            {t.calibration?.enabled
                                ? `operational prevalence ${t.calibration.operational_prevalence}`
                                : "set OPERATIONAL_PREVALENCE to emit prior-corrected risk"}
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <section>
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5"><ChartBar size={14} /> Global feature importance</h2>
                        <div className="tactical-card p-4 space-y-2" data-testid="mc-importance">
                            {importances.length ? importances.map(([f, v]) => (
                                <div key={f}>
                                    <div className="flex justify-between font-mono text-[11px]"><span>{f}</span><span className="text-[var(--text-2)]">{Number(v).toFixed(4)}</span></div>
                                    <div className="h-1.5 bg-white/5 mt-0.5"><div className="h-full bg-[var(--sev-high)]" style={{ width: `${Math.max(3, (v / maxImp) * 100)}%` }} /></div>
                                </div>
                            )) : <div className="font-mono text-[11px] text-[var(--text-2)]">Importance data unavailable in this build.</div>}
                            <div className="font-mono text-[9px] text-[var(--text-2)] pt-1 border-t border-[var(--border)]">src: {t.importance_source}</div>
                        </div>

                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 mt-4">Severity bands</h2>
                        <div className="tactical-card p-4 space-y-1.5" data-testid="mc-bands">
                            {(t.severity_bands || []).map(b => (
                                <div key={b.label} className="flex items-center gap-2">
                                    <span className={`chip ${{ LOW: "sev-low", MEDIUM: "sev-medium", HIGH: "sev-high", CRITICAL: "sev-critical" }[b.label] || "sev-unknown"}`}>{b.label}</span>
                                    <span className="font-mono text-[11px] text-[var(--text-2)]">{b.lo} ≤ p &lt; {b.hi >= 1 ? "1.0" : b.hi}</span>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section>
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5"><Info size={14} /> How it was trained</h2>
                        <div className="tactical-card p-4 space-y-2 text-sm" data-testid="mc-training">
                            <div><span className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">Design</span><div>{t.training?.design}</div></div>
                            <div className="grid grid-cols-3 gap-2 font-mono text-[11px]">
                                <div><div className="text-[var(--text-2)]">train prevalence</div><div className="text-white text-base">{t.training?.train_prevalence}</div></div>
                                <div><div className="text-[var(--text-2)]">positives</div><div className="text-white text-base">{t.training?.positives_kept ?? "—"}</div></div>
                                <div><div className="text-[var(--text-2)]">total rows</div><div className="text-white text-base">{t.training?.total_rows ?? "—"}</div></div>
                            </div>
                            <div className="text-[var(--text-2)] text-xs border-l-2 border-[var(--sev-medium)] pl-2">{t.training?.note}</div>
                            <div className="font-mono text-[9px] text-[var(--text-2)]">src: {t.training?.source}</div>
                        </div>

                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 mt-4 flex items-center gap-1.5 text-[var(--sev-high)]"><Warning size={14} /> NOT designed for</h2>
                        <div className="tactical-card p-4 border-l-2 border-[var(--sev-high)]" data-testid="mc-limits">
                            <ul className="space-y-1.5 text-sm">
                                {(t.not_designed_for || []).map((x, i) => (
                                    <li key={i} className="flex gap-2"><span className="text-[var(--sev-high)] font-bold">✕</span><span>{x}</span></li>
                                ))}
                            </ul>
                        </div>
                    </section>
                </div>

                <div className="tactical-card p-3" data-testid="mc-features">
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2">Full feature set ({t.feature_count})</div>
                    <div className="flex flex-wrap gap-1.5">
                        {(t.features || []).map(f => <span key={f} className="chip sev-unknown font-mono text-[10px]">{f}</span>)}
                    </div>
                </div>
            </div>
        </Shell>
    );
}
