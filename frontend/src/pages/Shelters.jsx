/**
 * Shelters — the authority-side register behind the public "where do I go?" page.
 *
 * The single most consequential field on this screen is occupancy, and the single
 * most consequential *non*-value is a blank one. If a camp's occupancy has never
 * been counted, this page says "not counted yet" in those words rather than
 * showing 0 — because the recommendation engine reads the same record, and a
 * fabricated zero is what sends a family at night to a camp that filled up hours
 * ago. Every control here is built so that clearing a field is impossible by
 * accident and leaving it unknown is honest by default.
 */
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";
import { Buildings, ArrowClockwise, Warning, CheckCircle, Info } from "@phosphor-icons/react";

const STATUSES = ["OPEN", "FULL", "STANDBY", "CLOSED"];
const STATUS_CLASS = { OPEN: "sev-low", FULL: "sev-high", STANDBY: "sev-medium", CLOSED: "sev-critical" };
const CATEGORY_LABEL = {
    RELIEF_CAMP: "Relief camp", SCHOOL: "School", COMMUNITY_HALL: "Community hall",
    HOSPITAL: "Hospital", HELIPAD: "Helipad", OTHER: "Shelter",
};

function occupancyLabel(s) {
    if (s.capacity === null || s.capacity === undefined) return "Capacity not recorded";
    if (s.current_occupancy === null || s.current_occupancy === undefined) return `Capacity ${s.capacity} · occupancy not counted yet`;
    const free = s.capacity - s.current_occupancy;
    return `${s.current_occupancy} / ${s.capacity} · ${free > 0 ? `${free} free` : "no spare space"}`;
}

function ShelterRow({ shelter, onSave, busy }) {
    const [occ, setOcc] = useState(
        shelter.current_occupancy === null || shelter.current_occupancy === undefined ? "" : String(shelter.current_occupancy),
    );
    const [status, setStatus] = useState(shelter.status);
    const dirty = status !== shelter.status
        || occ !== (shelter.current_occupancy === null || shelter.current_occupancy === undefined ? "" : String(shelter.current_occupancy));

    const save = () => {
        const changes = {};
        if (status !== shelter.status) changes.status = status;
        // An empty box means "I am not changing this", never "set it to zero".
        // To record an actually-empty shelter the operator types 0 explicitly.
        if (occ.trim() !== "" && Number(occ) !== shelter.current_occupancy) changes.current_occupancy = Number(occ);
        if (Object.keys(changes).length) onSave(shelter.shelter_id, changes);
    };

    const overfull = shelter.capacity != null && shelter.current_occupancy != null && shelter.current_occupancy > shelter.capacity;

    return (
        <div className="tactical-card p-4" data-testid={`shelter-${shelter.shelter_id}`}>
            <div className="flex items-start gap-3 flex-wrap">
                <div className="flex-1 min-w-[14rem]">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-heading font-bold tracking-tight">{shelter.name}</span>
                        <span className={`chip ${STATUS_CLASS[shelter.status] || "sev-unknown"}`}>{shelter.status}</span>
                        {shelter.source === "SEED_DEMO" && <span className="chip sev-unknown">DEMO DATA</span>}
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mt-1">
                        {shelter.shelter_id} · {CATEGORY_LABEL[shelter.category] || "Shelter"}
                        {shelter.district ? ` · ${shelter.district}` : ""}{shelter.state ? `, ${shelter.state}` : ""}
                    </div>
                    <div className="font-mono text-[11px] text-[var(--text-2)] mt-1">{occupancyLabel(shelter)}</div>
                    {overfull && (
                        <div className="flex items-center gap-1 text-[11px] text-[var(--sev-critical)] mt-1">
                            <Warning size={12} /> Occupancy exceeds recorded capacity.
                        </div>
                    )}
                </div>

                <div className="flex items-end gap-2 flex-wrap">
                    <label className="block">
                        <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-[var(--text-2)] block mb-1">Occupancy</span>
                        <input
                            type="number"
                            min="0"
                            value={occ}
                            onChange={(e) => setOcc(e.target.value)}
                            placeholder={shelter.current_occupancy == null ? "not counted" : ""}
                            data-testid={`occ-${shelter.shelter_id}`}
                            className="w-28 tactical-border bg-transparent px-2 py-1 text-xs font-mono focus:outline-none focus:border-white"
                        />
                    </label>
                    <label className="block">
                        <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-[var(--text-2)] block mb-1">Status</span>
                        <select
                            value={status}
                            onChange={(e) => setStatus(e.target.value)}
                            data-testid={`status-${shelter.shelter_id}`}
                            className="tactical-border bg-transparent px-2 py-1 text-xs font-mono focus:outline-none"
                        >
                            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                    </label>
                    <button
                        onClick={save}
                        disabled={busy || !dirty}
                        data-testid={`save-${shelter.shelter_id}`}
                        className="chip sev-low disabled:opacity-30"
                    >
                        <CheckCircle size={11} /> Save
                    </button>
                </div>
            </div>
        </div>
    );
}

export default function Shelters() {
    const [shelters, setShelters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState("");
    const [err, setErr] = useState("");

    const load = useCallback(async () => {
        setLoading(true); setErr("");
        try { setShelters((await api.get("/shelters")).data); }
        catch (e) { setErr("Could not load the shelter register."); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { load(); }, [load]);

    const save = async (shelterId, changes) => {
        setBusy(true); setMsg(""); setErr("");
        try {
            await api.patch(`/shelters/${shelterId}`, changes);
            setMsg(`${shelterId} updated.`);
            await load();
        } catch (e) { setErr(`Could not update ${shelterId}.`); }
        finally { setBusy(false); }
    };

    const uncounted = shelters.filter((s) => s.current_occupancy === null || s.current_occupancy === undefined).length;

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="shelters-page">
                <div className="flex items-end gap-4 flex-wrap">
                    <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Response · Shelter register</div>
                        <h1 className="font-heading text-3xl tracking-tighter font-bold">Shelters</h1>
                    </div>
                    <button onClick={load} disabled={loading} className="chip sev-low disabled:opacity-50 mb-1" data-testid="shelters-refresh">
                        <ArrowClockwise size={11} /> {loading ? "Loading…" : "Refresh"}
                    </button>
                </div>

                <div className="tactical-card p-4 flex items-center gap-6 flex-wrap" data-testid="shelters-summary">
                    <div>
                        <div className="font-heading text-2xl font-bold tracking-tighter">{shelters.length}</div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">On the register</div>
                    </div>
                    <div>
                        <div className="font-heading text-2xl font-bold tracking-tighter">{shelters.filter((s) => s.status === "OPEN").length}</div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">Open</div>
                    </div>
                    <div>
                        <div className="font-heading text-2xl font-bold tracking-tighter">{uncounted}</div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">Occupancy not counted</div>
                    </div>
                    {uncounted > 0 && (
                        <div className="flex items-start gap-2 text-xs text-[var(--sev-medium)] ml-auto max-w-md">
                            <Info size={14} className="mt-[1px] shrink-0" />
                            <span>
                                These are shown to the public as "occupancy not counted yet", never as empty.
                                Counting them is the highest-value thing you can do on this screen.
                            </span>
                        </div>
                    )}
                </div>

                {msg && <div className="tactical-card p-3 text-xs text-[var(--sev-low)]" data-testid="shelters-msg">{msg}</div>}
                {err && <div className="tactical-card p-3 text-xs text-[var(--sev-high)]" data-testid="shelters-error">{err}</div>}

                <div className="space-y-3">
                    {shelters.map((s) => <ShelterRow key={s.shelter_id} shelter={s} onSave={save} busy={busy} />)}
                    {!loading && !shelters.length && (
                        <div className="tactical-card p-8 text-center font-mono text-xs text-[var(--text-2)]" data-testid="shelters-empty">
                            <Buildings size={24} className="mx-auto mb-2" />
                            No shelters on the register. Run the seed migration or add them via POST /api/shelters.
                        </div>
                    )}
                </div>
            </div>
        </Shell>
    );
}
