import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Shell from "@/components/Shell";
import { api, severityClass } from "@/lib/api";

export default function Zones() {
    const nav = useNavigate();
    const [zones, setZones] = useState([]);
    const [sev, setSev] = useState("");
    const [state, setState] = useState("");

    useEffect(() => {
        const params = {};
        if (sev) params.severity = sev;
        if (state) params.state = state;
        api.get("/zones", { params }).then(r => setZones(r.data));
    }, [sev, state]);

    const states = [...new Set(zones.map(z => z.state))].sort();

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="zones-page">
                <div className="flex items-center gap-3 flex-wrap">
                    <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Zones</div>
                        <h1 className="font-heading text-3xl tracking-tighter font-bold">Monitored risk zones</h1>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                        <select value={state} onChange={e => setState(e.target.value)} data-testid="filter-state" className="tactical-border bg-transparent text-xs font-mono px-2 py-1 uppercase tracking-[0.15em]">
                            <option value="">All states</option>
                            {states.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                        <select value={sev} onChange={e => setSev(e.target.value)} data-testid="filter-severity" className="tactical-border bg-transparent text-xs font-mono px-2 py-1 uppercase tracking-[0.15em]">
                            <option value="">All severity</option>
                            {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                    </div>
                </div>
                <div className="tactical-card overflow-hidden">
                    <div className="overflow-x-auto">
                    <table className="w-full text-sm min-w-[720px]">
                        <thead className="border-b border-[var(--border)] font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">
                            <tr>
                                <th className="text-left px-3 py-2">Zone</th>
                                <th className="text-left px-3 py-2">District</th>
                                <th className="text-left px-3 py-2">State</th>
                                <th className="text-right px-3 py-2">Score</th>
                                <th className="text-left px-3 py-2">Severity</th>
                                <th className="text-right px-3 py-2">Pop</th>
                                <th className="text-right px-3 py-2">Updated</th>
                            </tr>
                        </thead>
                        <tbody>
                            {zones.map(z => (
                                <tr key={z.zone_id} onClick={() => nav(`/zones/${z.zone_id}`)} data-testid={`zone-row-${z.zone_id}`} className="border-b border-[var(--border)] hover:bg-white/[0.03] cursor-pointer">
                                    <td className="px-3 py-2 font-heading font-semibold">{z.name}</td>
                                    <td className="px-3 py-2">{z.district}</td>
                                    <td className="px-3 py-2 font-mono text-xs">{z.state}</td>
                                    <td className="px-3 py-2 text-right font-mono">{z.latest?.risk_score ?? "—"}</td>
                                    <td className="px-3 py-2"><span className={`chip ${severityClass(z.latest?.severity || "UNKNOWN")}`}>{z.latest?.severity || "UNKNOWN"}</span></td>
                                    <td className="px-3 py-2 text-right font-mono">{z.population}</td>
                                    <td className="px-3 py-2 text-right font-mono text-[10px] text-[var(--text-2)]">{z.latest?.updated_at?.slice(11, 16) || "—"}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    </div>
                </div>
            </div>
        </Shell>
    );
}
