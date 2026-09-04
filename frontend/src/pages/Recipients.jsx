import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";
import { Trash, PaperPlaneTilt, Broadcast } from "@phosphor-icons/react";

const LANG = { en: "English", as: "Assamese", kha: "Khasi", lus: "Mizo", ne: "Nepali", brx: "Bodo" };
const ROLES = ["AUTHORITY", "FIELD_OFFICER", "CITIZEN"];

export default function Recipients() {
    const [recipients, setRecipients] = useState([]);
    const [notifs, setNotifs] = useState([]);
    const [status, setStatus] = useState(null);
    const [form, setForm] = useState({ name: "", phone: "", role: "AUTHORITY", district: "", language: "en" });
    const [saving, setSaving] = useState(false);

    const load = async () => {
        const [r, n, s] = await Promise.all([
            api.get("/recipients"),
            api.get("/notifications?limit=50"),
            api.get("/notifications/status"),
        ]);
        setRecipients(r.data);
        setNotifs(n.data);
        setStatus(s.data);
    };
    useEffect(() => { load(); }, []);

    const add = async () => {
        if (!form.name || !form.phone) return;
        setSaving(true);
        try {
            await api.post("/recipients", { ...form, district: form.district || null });
            setForm({ name: "", phone: "", role: "AUTHORITY", district: "", language: "en" });
            await load();
        } finally { setSaving(false); }
    };

    const remove = async (id) => {
        await api.delete(`/recipients/${id}`);
        await load();
    };

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="recipients-page">
                <div className="flex items-center gap-3 flex-wrap">
                    <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Notifications</div>
                        <h1 className="font-heading text-3xl tracking-tighter font-bold">SMS distribution list</h1>
                    </div>
                    {status && (
                        <span className={`chip ${status.twilio_configured ? "sev-low" : "sev-medium"} ml-auto`} data-testid="sms-provider">
                            <Broadcast size={11} /> Provider: {status.provider}
                        </span>
                    )}
                </div>

                {!status?.twilio_configured && (
                    <div className="tactical-card p-3 border-l-2 border-[var(--sev-medium)] text-xs font-mono" data-testid="sms-mode-banner">
                        LOG_ONLY MODE — set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER in backend/.env then restart backend to enable real SMS delivery. Every alert is still logged with the exact message body per recipient in each recipient's preferred language.
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <section>
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2">Add recipient</h2>
                        <div className="tactical-card p-4 space-y-2" data-testid="add-form">
                            <input data-testid="rec-name" placeholder="Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="w-full tactical-border bg-transparent px-2 py-1.5 text-sm focus:outline-none focus:border-white" />
                            <input data-testid="rec-phone" placeholder="+91XXXXXXXXXX" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className="w-full tactical-border bg-transparent px-2 py-1.5 text-sm font-mono focus:outline-none focus:border-white" />
                            <input data-testid="rec-district" placeholder="District (blank = all districts)" value={form.district} onChange={e => setForm({ ...form, district: e.target.value })} className="w-full tactical-border bg-transparent px-2 py-1.5 text-sm focus:outline-none focus:border-white" />
                            <div className="grid grid-cols-2 gap-2">
                                <select data-testid="rec-role" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} className="tactical-border bg-transparent px-2 py-1.5 text-xs font-mono uppercase">
                                    {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                                </select>
                                <select data-testid="rec-lang" value={form.language} onChange={e => setForm({ ...form, language: e.target.value })} className="tactical-border bg-transparent px-2 py-1.5 text-xs font-mono uppercase">
                                    {Object.entries(LANG).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
                                </select>
                            </div>
                            <button onClick={add} disabled={saving} data-testid="add-btn" className="w-full py-2 bg-[var(--sev-critical)] text-white text-xs font-mono uppercase tracking-[0.15em] hover:bg-red-500 disabled:opacity-50">
                                {saving ? "Adding…" : "Add recipient"}
                            </button>
                        </div>
                    </section>

                    <section>
                        <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2">Current recipients ({recipients.length})</h2>
                        <div className="tactical-card divide-y divide-[var(--border)]" data-testid="recipient-list">
                            {recipients.map(r => (
                                <div key={r.id} className="p-3 flex items-center gap-2" data-testid={`rec-${r.id}`}>
                                    <div className="flex-1">
                                        <div className="font-heading font-semibold text-sm">{r.name}</div>
                                        <div className="font-mono text-[11px] text-[var(--text-2)]">{r.phone} · {r.role} · {LANG[r.language] || r.language}</div>
                                        <div className="font-mono text-[10px] text-[var(--text-2)]">District: {r.district || "ALL"}</div>
                                    </div>
                                    <button onClick={() => remove(r.id)} data-testid={`del-${r.id}`} className="p-1 text-[var(--text-2)] hover:text-[var(--sev-critical)]"><Trash size={14} /></button>
                                </div>
                            ))}
                            {!recipients.length && <div className="p-6 font-mono text-xs text-[var(--text-2)] text-center">No recipients yet. Add one to receive SMS on every alert.</div>}
                        </div>
                    </section>
                </div>

                <section>
                    <h2 className="font-heading text-sm uppercase tracking-[0.15em] font-semibold mb-2 flex items-center gap-1.5">
                        <PaperPlaneTilt size={14} /> Delivery ledger (last 50)
                    </h2>
                    <div className="tactical-card overflow-hidden" data-testid="notif-ledger">
                        <table className="w-full text-sm">
                            <thead className="border-b border-[var(--border)] font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">
                                <tr>
                                    <th className="text-left px-3 py-2">Time</th>
                                    <th className="text-left px-3 py-2">To</th>
                                    <th className="text-left px-3 py-2">Lang</th>
                                    <th className="text-left px-3 py-2">Zone</th>
                                    <th className="text-left px-3 py-2">Status</th>
                                    <th className="text-left px-3 py-2">Body</th>
                                </tr>
                            </thead>
                            <tbody>
                                {notifs.map(n => (
                                    <tr key={n.id} className="border-b border-[var(--border)]" data-testid={`notif-${n.id}`}>
                                        <td className="px-3 py-2 font-mono text-[11px] text-[var(--text-2)]">{new Date(n.timestamp).toLocaleString()}</td>
                                        <td className="px-3 py-2 font-mono text-[11px]">{n.phone}</td>
                                        <td className="px-3 py-2 font-mono text-[10px]">{n.language}</td>
                                        <td className="px-3 py-2 font-mono text-[10px]">{n.zone_id}</td>
                                        <td className="px-3 py-2"><span className={`chip ${n.status === "sent" ? "sev-low" : n.status === "log_only" ? "sev-medium" : "sev-critical"}`}>{n.status}</span></td>
                                        <td className="px-3 py-2 text-xs max-w-[24rem] truncate" title={n.body}>{n.body}</td>
                                    </tr>
                                ))}
                                {!notifs.length && <tr><td colSpan={6} className="text-center py-6 font-mono text-xs text-[var(--text-2)]">No deliveries yet. Issue an alert to see the fan-out here.</td></tr>}
                            </tbody>
                        </table>
                    </div>
                </section>
            </div>
        </Shell>
    );
}
