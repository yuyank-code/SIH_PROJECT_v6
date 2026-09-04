import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import Shell from "@/components/Shell";
import RiskMap from "@/components/RiskMap";
import { api } from "@/lib/api";

export default function MapPage() {
    const nav = useNavigate();
    const [layers, setLayers] = useState({ zones: true, sensors: true, roads: true, villages: true, reports: true });
    const [reports, setReports] = useState([]);
    const [search, setSearch] = useState("");
    const [focus, setFocus] = useState(null);
    const [zones, setZones] = useState([]);

    useEffect(() => {
        api.get("/reports?limit=100").then(r => setReports(r.data));
        api.get("/zones").then(r => setZones(r.data));
    }, []);

    const doSearch = () => {
        const q = search.toLowerCase();
        const z = zones.find(x =>
            x.name.toLowerCase().includes(q) ||
            x.district.toLowerCase().includes(q) ||
            x.state.toLowerCase().includes(q) ||
            x.zone_id.toLowerCase().includes(q));
        if (z) setFocus({ lat: z.centroid.lat, lon: z.centroid.lon, zoom: 11 });
    };

    const toggle = (k) => setLayers(p => ({ ...p, [k]: !p[k] }));

    return (
        <Shell>
            <div className="min-h-screen flex flex-col">
                <div className="px-4 md:px-6 py-3 tactical-border border-l-0 border-r-0 border-t-0 flex flex-col md:flex-row md:items-center gap-2 md:gap-3 flex-wrap">
                    <div className="font-heading text-base md:text-lg tracking-tighter font-bold">Risk Map</div>
                    <div className="flex gap-2 flex-1 min-w-0">
                        <input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && doSearch()}
                            placeholder="Search zone / district / state"
                            data-testid="map-search-input"
                            className="tactical-border bg-transparent px-2 py-1 text-sm font-mono flex-1 min-w-0 focus:outline-none focus:border-white"
                        />
                        <button onClick={doSearch} data-testid="map-search-btn" className="px-3 py-1.5 tactical-border text-xs font-mono uppercase tracking-[0.15em] hover:bg-white/5 shrink-0">Go</button>
                    </div>
                    <div className="flex items-center gap-x-3 gap-y-1 md:ml-auto flex-wrap font-mono text-[11px] uppercase tracking-[0.15em]">
                        {["zones", "sensors", "roads", "villages", "reports"].map(k => (
                            <label key={k} data-testid={`layer-${k}`} className="flex items-center gap-1 cursor-pointer">
                                <input type="checkbox" checked={layers[k]} onChange={() => toggle(k)} /> {k}
                            </label>
                        ))}
                    </div>
                </div>
                <div className="flex-1 min-h-[70vh]">
                    <RiskMap
                        onSelectZone={(id) => nav(`/zones/${id}`)}
                        reports={reports}
                        layers={layers}
                        focusTarget={focus}
                    />
                </div>
            </div>
        </Shell>
    );
}
