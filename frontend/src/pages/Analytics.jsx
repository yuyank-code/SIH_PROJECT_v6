import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, SEVERITY_COLORS } from "@/lib/api";
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, LineChart, Line } from "recharts";

export default function Analytics() {
    const [summary, setSummary] = useState(null);
    const [priorities, setPriorities] = useState([]);
    const [history, setHistory] = useState(null);

    useEffect(() => {
        api.get("/dashboard/summary").then(r => setSummary(r.data));
        api.get("/response/priorities").then(r => setPriorities(r.data));
        api.get("/weather/history", { params: { latitude: 25.57, longitude: 91.89, days: 30 } }).then(r => setHistory(r.data));
    }, []);

    if (!summary) return <Shell><div className="p-8 font-mono text-sm text-[var(--text-2)]">Loading analytics…</div></Shell>;

    const sevData = Object.entries(summary.severity_counts).filter(([, v]) => v > 0).map(([k, v]) => ({ name: k, value: v, color: SEVERITY_COLORS[k] }));
    const priorityData = ["P1", "P2", "P3", "P4"].map(p => ({ priority: p, count: priorities.filter(i => i.priority === p).length }));
    const rainData = history?.time?.map((t, i) => ({ day: t.slice(5), rain: history.precipitation_sum[i] || 0 })) || [];

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="analytics-page">
                <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Analytics</div>
                    <h1 className="font-heading text-3xl tracking-tighter font-bold">Risk analytics</h1>
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mt-1">
                        Real data: Open-Meteo, V5 model outputs · DEMO data: sensors, terrain, roads (clearly labelled)
                    </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="tactical-card p-4">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2">Severity distribution</div>
                        <ResponsiveContainer width="100%" height={200}>
                            <PieChart>
                                <Pie data={sevData} dataKey="value" nameKey="name" innerRadius={40} outerRadius={70}>
                                    {sevData.map((e, i) => <Cell key={i} fill={e.color} />)}
                                </Pie>
                                <Tooltip contentStyle={{ background: "#131820", border: "1px solid #262e3b" }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="tactical-card p-4">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2">Response priority stack</div>
                        <ResponsiveContainer width="100%" height={200}>
                            <BarChart data={priorityData}>
                                <XAxis dataKey="priority" stroke="#9ca3af" style={{ fontFamily: "JetBrains Mono", fontSize: 11 }} />
                                <YAxis stroke="#9ca3af" style={{ fontFamily: "JetBrains Mono", fontSize: 11 }} />
                                <Tooltip contentStyle={{ background: "#131820", border: "1px solid #262e3b" }} />
                                <Bar dataKey="count" fill="#e11d48" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="tactical-card p-4">
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2">Rainfall 30d · Shillong (Open-Meteo)</div>
                        <ResponsiveContainer width="100%" height={200}>
                            <LineChart data={rainData}>
                                <XAxis dataKey="day" stroke="#9ca3af" style={{ fontFamily: "JetBrains Mono", fontSize: 10 }} interval={4} />
                                <YAxis stroke="#9ca3af" style={{ fontFamily: "JetBrains Mono", fontSize: 10 }} />
                                <Tooltip contentStyle={{ background: "#131820", border: "1px solid #262e3b" }} />
                                <Line type="monotone" dataKey="rain" stroke="#60a5fa" strokeWidth={1.5} dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>
                <div className="tactical-card p-4">
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2">Note</div>
                    <p className="text-sm leading-relaxed">Analytics is derived from V5 model outputs and Open-Meteo weather. Precision/recall for the model at threshold=0.15 (matched-pair evaluation): P=0.57, R=0.98. Operational precision on real deployment will differ — see model report for prior-correction.</p>
                </div>
            </div>
        </Shell>
    );
}
