import { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { MapTrifold, Waveform, Warning, HardDrives, FileText, Broadcast, ChartLineUp, Buildings, Users, SignOut, PaperPlaneTilt, List, X, Pulse, FirstAid, Brain } from "@phosphor-icons/react";
import { auth, roleFromStorage, setRole } from "@/lib/api";

const NAV = [
    { to: "/dashboard", label: "Overview", icon: ChartLineUp, testid: "nav-overview" },
    { to: "/map", label: "Risk Map", icon: MapTrifold, testid: "nav-map" },
    { to: "/ops", label: "Live Ops", icon: Pulse, testid: "nav-ops" },
    { to: "/zones", label: "Zones", icon: Buildings, testid: "nav-zones" },
    { to: "/sensors", label: "Sensors", icon: HardDrives, testid: "nav-sensors" },
    { to: "/reports", label: "Reports", icon: FileText, testid: "nav-reports" },
    { to: "/alerts", label: "Alerts", icon: Broadcast, testid: "nav-alerts" },
    { to: "/response", label: "Response", icon: Warning, testid: "nav-response" },
    { to: "/shelters", label: "Shelters", icon: Buildings, testid: "nav-shelters" },
    { to: "/recovery", label: "Recovery", icon: FirstAid, testid: "nav-recovery" },
    { to: "/model", label: "Model Card", icon: Brain, testid: "nav-model" },
    { to: "/analytics", label: "Analytics", icon: Waveform, testid: "nav-analytics" },
    { to: "/recipients", label: "Recipients", icon: PaperPlaneTilt, testid: "nav-recipients" },
];

export default function Shell({ children }) {
    const nav = useNavigate();
    const loc = useLocation();
    const role = roleFromStorage();
    const [open, setOpen] = useState(false);
    const [loggingOut, setLoggingOut] = useState(false);

    useEffect(() => { setOpen(false); }, [loc.pathname]);

    const logout = async () => {
        if (loggingOut) return;
        setLoggingOut(true);
        try {
            await auth.signOut();
        } finally {
            setRole("");
            nav("/login", { replace: true });
        }
    };

    const Sidebar = ({ mobile = false }) => (
        <aside className={`tactical-panel flex flex-col ${mobile ? "w-[80vw] max-w-[280px] h-full" : "h-screen sticky top-0 w-[220px] hidden lg:flex"}`} data-testid={mobile ? "mobile-drawer" : "sidebar"}>
            <div className="px-4 py-4 border-b border-[var(--border)] flex items-center justify-between">
                <Link to="/dashboard" className="flex items-center gap-2" data-testid="brand-link">
                    <div className="w-8 h-8 flex items-center justify-center bg-[var(--sev-critical)] text-white font-heading font-bold text-sm">NS</div>
                    <div>
                        <div className="font-heading font-bold tracking-tighter text-sm leading-tight">NER-SLIDE</div>
                        <div className="font-mono text-[10px] text-[var(--text-2)] uppercase tracking-[0.15em]">Early Warning Ops</div>
                    </div>
                </Link>
                {mobile && (
                    <button onClick={() => setOpen(false)} data-testid="close-drawer" className="text-[var(--text-2)] p-1"><X size={20} /></button>
                )}
            </div>
            <nav className="flex-1 py-2 overflow-y-auto">
                {NAV.map(({ to, label, icon: Icon, testid }) => {
                    const active = loc.pathname.startsWith(to);
                    return (
                        <Link key={to} to={to} data-testid={testid} className={`flex items-center gap-2 px-4 py-2.5 text-sm transition-colors ${active ? "bg-white/5 text-white border-l-2 border-[var(--sev-critical)]" : "text-[var(--text-2)] hover:text-white hover:bg-white/[0.03] border-l-2 border-transparent"}`}>
                            <Icon size={16} weight="regular" />
                            <span>{label}</span>
                        </Link>
                    );
                })}
            </nav>
            <div className="border-t border-[var(--border)] p-3 space-y-2">
                <Link to="/public" className="block text-xs font-mono uppercase tracking-widest text-[var(--text-2)] hover:text-white" data-testid="link-public"><Users size={12} className="inline mr-1" /> Citizen Portal</Link>
                <Link to="/field" className="block text-xs font-mono uppercase tracking-widest text-[var(--text-2)] hover:text-white" data-testid="link-field"><MapTrifold size={12} className="inline mr-1" /> Field Officer</Link>
                <Link to="/safety" className="block text-xs font-mono uppercase tracking-widest text-[var(--text-2)] hover:text-white" data-testid="link-safety"><Buildings size={12} className="inline mr-1" /> Safe Route</Link>
                <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-2)] pt-2 border-t border-[var(--border)]">Signed in as <span className="text-white">{role || "GUEST"}</span></div>
                <button onClick={logout} disabled={loggingOut} data-testid="btn-logout" className="w-full text-left text-xs font-mono uppercase tracking-widest text-[var(--text-2)] hover:text-white flex items-center gap-1 disabled:opacity-50">
                    <SignOut size={12} /> {loggingOut ? "Signing out..." : "Sign out"}
                </button>
            </div>
        </aside>
    );

    return (
        <div className="min-h-screen flex" data-testid="app-shell">
            <Sidebar />
            <div className="lg:hidden fixed top-0 left-0 right-0 z-40 bg-[var(--bg)] border-b border-[var(--border)] px-3 py-2 flex items-center gap-3">
                <button onClick={() => setOpen(true)} data-testid="open-drawer" className="p-1 text-white"><List size={22} /></button>
                <Link to="/dashboard" className="flex items-center gap-2"><div className="w-7 h-7 flex items-center justify-center bg-[var(--sev-critical)] text-white font-heading font-bold text-xs">NS</div><div className="font-heading font-bold tracking-tighter text-sm leading-tight">NER-SLIDE</div></Link>
                <div className="ml-auto font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">{role || "GUEST"}</div>
            </div>
            {open && <div className="lg:hidden fixed inset-0 z-50 flex" onClick={() => setOpen(false)}><div onClick={(e) => e.stopPropagation()}><Sidebar mobile /></div><div className="flex-1 bg-black/50 backdrop-blur-sm" /></div>}
            <main className="flex-1 min-h-screen overflow-y-auto pt-12 lg:pt-0">{children}</main>
        </div>
    );
}
