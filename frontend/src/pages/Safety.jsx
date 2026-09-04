/**
 * Safety — "the system says my area is risky, where do I actually go?"
 *
 * This page is the citizen-facing answer to that question. Three design rules
 * shaped it, all of them downstream of *who is reading it*: someone frightened,
 * possibly in the rain, on a cheap phone, on one bar of signal.
 *
 *  1. No sign-in. It reads /public/safe-route. A login wall between a person and
 *     an evacuation instruction is indefensible.
 *  2. The action comes first, the evidence second. Immediate steps sit above the
 *     shelter list, because a person scrolling in a panic reads the top and goes.
 *  3. Unknowns are printed, not hidden. "Occupancy not counted yet" is shown as
 *     those words. A blank space would be read as "fine", and it isn't.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, severityClass } from "@/lib/api";
import {
    MapPin, Warning, WarningCircle, ShieldCheck, PersonSimpleWalk,
    ArrowLeft, Path, Info, CheckCircle, XCircle, ArrowClockwise, Buildings,
} from "@phosphor-icons/react";

const CATEGORY_LABEL = {
    RELIEF_CAMP: "Relief camp", SCHOOL: "School", COMMUNITY_HALL: "Community hall",
    HOSPITAL: "Hospital", HELIPAD: "Helipad", OTHER: "Shelter",
};

const STATUS_CLASS = {
    OPEN: "sev-low", FULL: "sev-high", CLOSED: "sev-critical", STANDBY: "sev-medium",
};

/** Walking time, or the honest reason there isn't one. */
function walkLabel(shelter) {
    if (shelter.requires_transport) return "Too far to walk";
    if (shelter.walk_minutes_estimate === null || shelter.walk_minutes_estimate === undefined) return "Walk time unknown";
    const m = shelter.walk_minutes_estimate;
    return m < 60 ? `~${m} min walk` : `~${Math.floor(m / 60)}h ${m % 60}m walk`;
}

/** Spare capacity phrased so a missing count never reads as "empty". */
function capacityLabel(view) {
    if (!view) return "Capacity unknown";
    if (!view.known) return view.note || "Capacity unknown";
    if (view.headroom === null || view.headroom === undefined) return "Capacity unknown";
    if (view.headroom <= 0) return "No spare space recorded";
    return `${view.headroom} of ${view.capacity} places free`;
}

function ShelterCard({ shelter, primary }) {
    const cat = CATEGORY_LABEL[shelter.category] || CATEGORY_LABEL.OTHER;
    return (
        <div
            className={`tactical-card p-4 ${primary ? "border-[var(--sev-low)]" : ""}`}
            data-testid={`shelter-${shelter.shelter_id}`}
        >
            <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-heading font-bold tracking-tight">{shelter.name}</span>
                        <span className={`chip ${STATUS_CLASS[shelter.status] || "sev-unknown"}`}>{shelter.status}</span>
                        {shelter.source === "SEED_DEMO" && <span className="chip sev-unknown">DEMO DATA</span>}
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mt-1">
                        {cat}{shelter.district ? ` · ${shelter.district}` : ""}{shelter.state ? `, ${shelter.state}` : ""}
                    </div>
                </div>
                <div className="text-right shrink-0">
                    <div className="font-heading font-bold text-xl tracking-tighter">
                        {shelter.distance_km !== null && shelter.distance_km !== undefined ? `${shelter.distance_km} km` : "—"}
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">
                        {shelter.direction ? `head ${shelter.direction}` : "direction unknown"}
                    </div>
                </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap mt-3 font-mono text-[11px] text-[var(--text-2)]">
                <span className="flex items-center gap-1"><PersonSimpleWalk size={12} /> {walkLabel(shelter)}</span>
                <span className="flex items-center gap-1"><Buildings size={12} /> {capacityLabel(shelter.capacity_view)}</span>
                {shelter.contact_phone && (
                    <a href={`tel:${shelter.contact_phone}`} className="underline hover:text-white" data-testid={`call-${shelter.shelter_id}`}>
                        Call {shelter.contact_phone}
                    </a>
                )}
            </div>

            {shelter.warnings?.length > 0 && (
                <div className="mt-3 space-y-1">
                    {shelter.warnings.map((w, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-[var(--sev-high)]">
                            <WarningCircle size={13} className="mt-[2px] shrink-0" /><span>{w}</span>
                        </div>
                    ))}
                </div>
            )}

            {/* The score is shown with its arithmetic, or not at all. A number a
                person cannot interrogate is a number they are being asked to obey. */}
            <details className="mt-3">
                <summary className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] cursor-pointer hover:text-white">
                    Suitability {shelter.suitability}/100 · why?
                </summary>
                <ul className="mt-2 text-[11px] text-[var(--text-2)] list-disc pl-4 space-y-[2px]">
                    {shelter.reasons?.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
                <div className="mt-2 font-mono text-[10px] text-[var(--text-2)]">{shelter.walk_estimate_basis}</div>
            </details>
        </div>
    );
}

export default function Safety() {
    const [pos, setPos] = useState(null);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const load = useCallback(async (lat, lon) => {
        setLoading(true); setError("");
        try {
            const { data: res } = await api.get("/public/safe-route", { params: { lat, lon, limit: 6 } });
            setData(res);
        } catch (e) {
            setError("Could not reach the server. If you have no signal, follow the steps below anyway — they do not need a network.");
        } finally { setLoading(false); }
    }, []);

    const locate = useCallback(() => {
        if (!navigator.geolocation) { setError("This device cannot report its location. Ask someone nearby with GPS."); return; }
        setLoading(true); setError("");
        navigator.geolocation.getCurrentPosition(
            (p) => { const c = { lat: p.coords.latitude, lon: p.coords.longitude }; setPos(c); load(c.lat, c.lon); },
            () => { setLoading(false); setError("Location permission denied. Allow location access so we can find shelters near you."); },
            { enableHighAccuracy: true, timeout: 10000 },
        );
    }, [load]);

    useEffect(() => { locate(); }, [locate]);

    const originSev = data?.origin_risk?.severity;
    const urgent = ["CRITICAL", "HIGH"].includes(originSev);

    return (
        <div className="min-h-screen bg-[var(--bg)] pb-16" data-testid="safety-page">
            <header className="sticky top-0 z-10 bg-[var(--bg)] border-b border-[var(--border)] px-4 py-3 flex items-center gap-3">
                <Link to="/public" className="text-[var(--text-2)]" data-testid="safety-back"><ArrowLeft size={18} /></Link>
                <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">NER-SLIDE · Public safety</div>
                    <div className="font-heading font-bold text-lg tracking-tighter">Where do I go?</div>
                </div>
                <button onClick={locate} disabled={loading} data-testid="safety-refresh" className="ml-auto chip sev-low disabled:opacity-50">
                    <ArrowClockwise size={11} /> {loading ? "Locating…" : "Refresh"}
                </button>
            </header>

            <div className="max-w-2xl mx-auto p-4 space-y-4">
                {/* --- where you are, and whether that is a problem --- */}
                <div className="tactical-card p-4" data-testid="safety-origin">
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2 flex items-center gap-1">
                        <MapPin size={12} /> Your location
                    </div>
                    {pos ? (
                        <>
                            <div className="font-mono text-xs">{pos.lat.toFixed(5)}, {pos.lon.toFixed(5)}</div>
                            {data?.origin_risk ? (
                                <div className="mt-2 flex items-center gap-2 flex-wrap">
                                    <span className={`chip ${severityClass(originSev)}`}>{originSev || "NOT ASSESSED"}</span>
                                    <span className="text-xs">
                                        {data.origin_risk.distance_km} km from <b>{data.origin_risk.name}</b>
                                    </span>
                                </div>
                            ) : (
                                <div className="mt-2 text-xs text-[var(--text-2)]">
                                    You are not inside any zone this system monitors. That means <b>no assessment exists here</b> — it does not mean the ground is safe.
                                </div>
                            )}
                        </>
                    ) : (
                        <button onClick={locate} data-testid="safety-locate" className="w-full py-3 tactical-border bg-white/[0.03] font-mono uppercase tracking-[0.15em] text-sm hover:bg-white/[0.06] flex items-center justify-center gap-2">
                            <MapPin size={16} /> Find my location
                        </button>
                    )}
                    {error && <div className="mt-2 text-xs text-[var(--sev-high)]" data-testid="safety-error">{error}</div>}
                </div>

                {/* --- the banner, only when it is earned --- */}
                {urgent && (
                    <div className="tactical-card p-4 border-[var(--sev-critical)]" data-testid="safety-urgent">
                        <div className="flex items-center gap-2 font-heading font-bold text-lg tracking-tight text-[var(--sev-critical)]">
                            <Warning size={20} /> Leave now
                        </div>
                        <p className="text-sm mt-1">
                            Your location is inside a zone currently rated {originSev}. Do not wait for a siren or an official instruction.
                        </p>
                    </div>
                )}

                {/* --- what to do, before where to go --- */}
                {data?.guidance?.length > 0 && (
                    <div className="tactical-card p-4" data-testid="safety-guidance">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-3 flex items-center gap-1">
                            <Path size={12} /> Do this now, in order
                        </div>
                        <ol className="space-y-3">
                            {data.guidance.map((g) => (
                                <li key={g.code} className="flex items-start gap-3" data-testid={`guidance-${g.code}`}>
                                    <span className="font-heading font-bold text-sm w-6 h-6 shrink-0 flex items-center justify-center tactical-border">
                                        {g.priority}
                                    </span>
                                    <span className="text-sm leading-relaxed">{g.text}</span>
                                </li>
                            ))}
                        </ol>
                    </div>
                )}

                {/* --- the recommendation --- */}
                {data?.recommended && (
                    <div data-testid="safety-recommended">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2 flex items-center gap-1">
                            <CheckCircle size={12} /> {data.transport_only ? "Closest option — needs transport" : "Go here"}
                        </div>
                        <ShelterCard shelter={data.recommended} primary />
                    </div>
                )}

                {data && !data.recommended && (
                    <div className="tactical-card p-4" data-testid="safety-none">
                        <div className="flex items-center gap-2 text-[var(--sev-high)] font-heading font-bold">
                            <XCircle size={16} /> No shelter is on record near you
                        </div>
                        <p className="text-sm mt-2 leading-relaxed">
                            This system has no shelter recorded within reach of your location. That is a gap in the
                            data, not proof that nowhere is safe. Move to open, level ground away from slopes and
                            call your district emergency helpline.
                        </p>
                    </div>
                )}

                {/* --- known blocked roads --- */}
                {data?.hazards?.length > 0 && (
                    <div className="tactical-card p-4" data-testid="safety-hazards">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2 flex items-center gap-1">
                            <WarningCircle size={12} /> Roads to avoid
                        </div>
                        <div className="space-y-2">
                            {data.hazards.map((h) => (
                                <div key={h.road_id} className="flex items-start gap-2 text-xs">
                                    <span className={`chip ${h.status === "BLOCKED" ? "sev-critical" : "sev-medium"}`}>{h.status}</span>
                                    <span><b>{h.name}</b>{h.distance_km !== null ? ` · ${h.distance_km} km away` : ""} — {h.advice}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* --- the rest of the list --- */}
                {data?.shelters?.length > 1 && (
                    <div className="space-y-3" data-testid="safety-alternatives">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] flex items-center gap-1">
                            <ShieldCheck size={12} /> Other shelters
                        </div>
                        {data.shelters
                            .filter((s) => s.shelter_id !== data.recommended?.shelter_id)
                            .map((s) => <ShelterCard key={s.shelter_id} shelter={s} />)}
                    </div>
                )}

                {/* --- say plainly what this is and is not --- */}
                {data?.assumptions && (
                    <div className="tactical-card p-4" data-testid="safety-assumptions">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2 flex items-center gap-1">
                            <Info size={12} /> How these directions were worked out
                        </div>
                        <p className="text-[11px] leading-relaxed text-[var(--text-2)]">{data.assumptions.routing}</p>
                        <p className="text-[11px] leading-relaxed text-[var(--text-2)] mt-2">
                            Walking times assume {data.assumptions.walking_pace_kmh} km/h in a straight line, so treat
                            them as a minimum. Anything more than {data.assumptions.walkable_radius_km} km is marked as
                            needing transport.
                        </p>
                    </div>
                )}

                <div className="flex gap-2">
                    <Link to="/report" className="flex-1 text-center py-3 tactical-border font-mono uppercase tracking-[0.15em] text-xs hover:bg-white/5" data-testid="safety-to-report">
                        Report what you can see
                    </Link>
                    <Link to="/public" className="flex-1 text-center py-3 tactical-border font-mono uppercase tracking-[0.15em] text-xs hover:bg-white/5">
                        Risk map
                    </Link>
                </div>
            </div>
        </div>
    );
}
