import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { auth, setRole } from "@/lib/api";
import { ShieldCheck, PersonSimpleWalk, UserCircle, Wrench as WrenchIcon } from "@phosphor-icons/react";

const ROUTES = { ADMIN: "/dashboard", AUTHORITY: "/dashboard", FIELD_OFFICER: "/field", CITIZEN: "/public" };
const ROLE_INFO = [
    { id: "AUTHORITY", label: "Authority", desc: "District & disaster management authorities.", icon: ShieldCheck },
    { id: "FIELD_OFFICER", label: "Field Officer", desc: "GPS + photo reporting and offline-first field work.", icon: PersonSimpleWalk },
    { id: "CITIZEN", label: "Citizen", desc: "Public risk map and community reporting.", icon: UserCircle },
    { id: "ADMIN", label: "Admin", desc: "System operator and model controls.", icon: WrenchIcon },
];

export default function Login() {
    const nav = useNavigate();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [fullName, setFullName] = useState("");
    const [mode, setMode] = useState("signin");
    const [loading, setLoading] = useState(false);
    const [msg, setMsg] = useState("");

    useEffect(() => {
        auth.session().then(async ({ data }) => {
            if (!data.session) return;
            try {
                const { data: me } = await auth.profile();
                const role = me.profile.role;
                setRole(role);
                nav(ROUTES[role] || "/public", { replace: true });
            } catch { /* stale session will be handled by the next auth request */ }
        });
    }, [nav]);

    const submit = async (e) => {
        e.preventDefault(); setLoading(true); setMsg("");
        try {
            const result = mode === "signin"
                ? await auth.signIn(email.trim(), password)
                : await auth.signUp(email.trim(), password, fullName.trim());
            if (result.error) throw result.error;
            if (mode === "signup" && !result.data?.session) {
                setMsg("Account created. Check your email to confirm, then sign in.");
                setMode("signin");
                return;
            }
            const { data: me } = await auth.profile();
            const role = me.profile.role;
            setRole(role);
            nav(ROUTES[role] || "/public", { replace: true });
        } catch (error) {
            setMsg(error?.message || "Authentication failed.");
        } finally { setLoading(false); }
    };

    return (
        <div className="min-h-screen topo-bg flex items-center justify-center px-4" data-testid="login-page">
            <div className="max-w-5xl w-full">
                <div className="flex items-center gap-3 mb-8">
                    <div className="w-10 h-10 flex items-center justify-center bg-[var(--sev-critical)] text-white font-heading font-bold">NS</div>
                    <div><div className="font-heading text-3xl md:text-4xl tracking-tighter font-bold">NER-SLIDE</div><div className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--text-2)]">AI Landslide Early Warning · North East India</div></div>
                </div>
                <div className="grid lg:grid-cols-2 gap-4">
                    <form onSubmit={submit} className="tactical-card p-6 md:p-8 space-y-4">
                        <div className="font-mono uppercase tracking-[0.15em] text-xs text-[var(--text-2)]">{mode === "signin" ? "Secure sign-in" : "Create citizen account"}</div>
                        {mode === "signup" && <input value={fullName} onChange={e=>setFullName(e.target.value)} required placeholder="Full name" className="w-full tactical-border bg-transparent p-3 text-sm" />}
                        <input value={email} onChange={e=>setEmail(e.target.value)} required type="email" placeholder="Email" className="w-full tactical-border bg-transparent p-3 text-sm" />
                        <input value={password} onChange={e=>setPassword(e.target.value)} required minLength={6} type="password" placeholder="Password" className="w-full tactical-border bg-transparent p-3 text-sm" />
                        <button disabled={loading} className="w-full py-3 bg-[var(--sev-critical)] text-white font-mono uppercase tracking-[0.15em] text-sm disabled:opacity-50">{loading ? "Authenticating…" : mode === "signin" ? "Sign in" : "Create account"}</button>
                        {msg && <div className="font-mono text-xs text-center text-[var(--text-2)]">{msg}</div>}
                        <button type="button" onClick={()=>{setMode(mode === "signin" ? "signup" : "signin");setMsg("");}} className="w-full text-xs font-mono uppercase tracking-[0.12em] text-[var(--text-2)] hover:text-white">{mode === "signin" ? "Create a citizen account" : "Back to sign in"}</button>
                    </form>
                    <div className="tactical-card p-6 md:p-8">
                        <div className="font-mono uppercase tracking-[0.15em] text-xs text-[var(--text-2)] mb-4">Server-assigned roles</div>
                        <div className="space-y-2">{ROLE_INFO.map(({id,label,desc,icon:Icon}) => <div key={id} className="p-3 border border-[var(--border)] flex items-start gap-3"><Icon size={22}/><div><div className="font-heading font-semibold">{label}</div><div className="text-sm text-[var(--text-2)]">{desc}</div></div></div>)}</div>
                        <div className="mt-5 pt-4 border-t border-[var(--border)] font-mono text-[10px] text-[var(--text-2)] uppercase tracking-[0.12em]">Role is read from the protected Supabase profile. It cannot be selected from the browser.</div>
                    </div>
                </div>
            </div>
        </div>
    );
}
