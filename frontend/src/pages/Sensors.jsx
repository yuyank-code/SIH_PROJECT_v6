import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";
import { BatteryHigh as Battery, HardDrives } from "@phosphor-icons/react";

export default function Sensors() {
    const [sensors, setSensors] = useState([]);
    const [filter, setFilter] = useState("");
    useEffect(() => { api.get("/sensors", { params: filter ? { status: filter } : {} }).then(r => setSensors(r.data)); }, [filter]);

    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="sensors-page">
                <div className="flex items-center gap-3 flex-wrap">
                    <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Ground Sensors</div>
                        <h1 className="font-heading text-3xl tracking-tighter font-bold">Sensor network health</h1>
                        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--sev-medium)] mt-1">Source: DEMO · replace with real MQTT/LoRaWAN ingest</div>
                    </div>
                    <select value={filter} onChange={e => setFilter(e.target.value)} data-testid="filter-status" className="ml-auto tactical-border bg-transparent text-xs font-mono px-2 py-1 uppercase tracking-[0.15em]">
                        <option value="">All</option>
                        <option value="ONLINE">Online</option>
                        <option value="OFFLINE">Offline</option>
                    </select>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                    {sensors.map(s => (
                        <div key={s.sensor_id} className="tactical-card p-4" data-testid={`sensor-${s.sensor_id}`}>
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="font-mono text-xs text-[var(--text-2)]">{s.sensor_id}</div>
                                    <div className="font-heading font-semibold">{s.type}</div>
                                </div>
                                <span className={`chip ${s.status === "ONLINE" ? "sev-low" : "sev-unknown"}`}>{s.status}</span>
                            </div>
                            <div className="font-mono text-xs text-[var(--text-2)] mt-2 flex items-center gap-1">
                                <HardDrives size={12} /> Zone {s.zone_id}
                            </div>
                            <div className="font-mono text-xs mt-1 flex items-center gap-1">
                                <Battery size={12} /> {s.battery}% · lat {s.lat.toFixed(3)}, lon {s.lon.toFixed(3)}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </Shell>
    );
}
