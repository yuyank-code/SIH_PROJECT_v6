import { useEffect, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { SEVERITY_COLORS, api } from "@/lib/api";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
    iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
    shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function FlyTo({ target }) {
    const map = useMap();
    useEffect(() => {
        const timer = setTimeout(() => map.invalidateSize(), 100);
        if (target) map.flyTo([target.lat, target.lon], target.zoom || 10, { duration: 1.2 });
        return () => clearTimeout(timer);
    }, [target, map]);
    return null;
}

export default function RiskMap({
    onSelectZone,
    focusTarget,
    reports = [],
    height = "100%",
    showLegend = true,
    publicMode = false,
    layers = { zones: true, sensors: true, roads: true, villages: true, reports: true, shelters: true },
}) {
    const [zonesFC, setZones] = useState(null);
    const [sensorsFC, setSensors] = useState(null);
    const [roadsFC, setRoads] = useState(null);
    const [villagesFC, setVillages] = useState(null);
    const [sheltersFC, setShelters] = useState(null);
    const [heatPts, setHeatPts] = useState([]);
    const [mapError, setMapError] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            const prefix = publicMode ? "/public/gis" : "/gis";
            const requests = [
                api.get(`${prefix}/risk-zones`),
                api.get(`${prefix}/roads`),
                api.get(`${prefix}/villages`),
                api.get(`${prefix}/heatmap`),
                // Appended last on purpose: the reads below are indexed
                // positionally, and the sensors splice already shifts them.
                // Keeping shelters at the tail means one index, both modes.
                api.get(`${prefix}/shelters`),
            ];
            if (!publicMode) requests.splice(1, 0, api.get("/gis/sensors"));

            const results = await Promise.allSettled(requests);
            if (cancelled) return;

            const value = (index) => results[index]?.status === "fulfilled" ? results[index].value.data : null;
            setShelters(value(requests.length - 1));
            if (publicMode) {
                setZones(value(0));
                setRoads(value(1));
                setVillages(value(2));
                setHeatPts(value(3) || []);
            } else {
                setZones(value(0));
                setSensors(value(1));
                setRoads(value(2));
                setVillages(value(3));
                setHeatPts(value(4) || []);
            }
            setMapError(results.every(r => r.status === "rejected"));
        };
        load();
        return () => { cancelled = true; };
    }, [publicMode]);

    const styleZone = (f) => {
        const sev = f.properties?.severity || "UNKNOWN";
        const color = SEVERITY_COLORS[sev] || "#6b7280";
        return { color, weight: 1.5, fillColor: color, fillOpacity: sev === "UNKNOWN" ? 0.08 : 0.28 };
    };

    return (
        <div className="relative w-full min-h-[70vh] overflow-hidden" style={{ height }} data-testid="risk-map">
            <MapContainer
                center={[26.2, 92.5]}
                zoom={7}
                scrollWheelZoom
                preferCanvas
                className="risk-leaflet-map"
                style={{ height: "100%", width: "100%", minHeight: "70vh", background: "#0a0c10" }}
            >
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                    maxZoom={19}
                />

                {layers.zones && zonesFC?.features?.length > 0 && <GeoJSON
                    data={zonesFC}
                    style={styleZone}
                    onEachFeature={(f, layer) => {
                        const p = f.properties || {};
                        layer.bindTooltip(`${p.name || "Zone"} • ${p.severity || "UNKNOWN"}`);
                        layer.on("click", () => onSelectZone && onSelectZone(p.zone_id));
                    }}
                />}

                {layers.zones && heatPts.map((h, i) => {
                    if (!h?.intensity || !Number.isFinite(Number(h.lat)) || !Number.isFinite(Number(h.lon))) return null;
                    const r = 6 + Number(h.intensity) * 22;
                    const color = SEVERITY_COLORS[h.severity] || "#6b7280";
                    return <CircleMarker key={`heat-${h.zone_id || i}`} center={[h.lat, h.lon]} radius={r} pathOptions={{ color, fillColor: color, fillOpacity: 0.28, weight: 0.5 }} />;
                })}

                {layers.roads && roadsFC?.features?.length > 0 && <GeoJSON
                    data={roadsFC}
                    style={(f) => ({
                        color: f.properties?.status === "BLOCKED" ? "#e11d48" : f.properties?.status === "AT_RISK" ? "#d97706" : "#60a5fa",
                        weight: 3,
                        dashArray: f.properties?.status === "BLOCKED" ? "6 4" : undefined,
                    })}
                    onEachFeature={(f, layer) => layer.bindTooltip(`${f.properties?.name || "Road"} • ${f.properties?.status || "UNKNOWN"}`)}
                />}

                {layers.sensors && !publicMode && sensorsFC?.features?.map((f, i) => {
                    const c = f.geometry?.coordinates;
                    if (!c || c.length < 2) return null;
                    const online = f.properties?.status === "ONLINE";
                    return <CircleMarker key={`sen-${i}`} center={[c[1], c[0]]} radius={4} pathOptions={{ color: online ? "#10b981" : "#6b7280", fillColor: online ? "#10b981" : "#6b7280", fillOpacity: 0.9 }}>
                        <Popup><div className="font-mono text-xs"><div className="font-bold">{f.properties?.sensor_id}</div><div>{f.properties?.type}</div><div>Status: {f.properties?.status}</div></div></Popup>
                    </CircleMarker>;
                })}

                {layers.villages && villagesFC?.features?.map((f, i) => {
                    const c = f.geometry?.coordinates;
                    if (!c || c.length < 2) return null;
                    return <CircleMarker key={`vil-${i}`} center={[c[1], c[0]]} radius={3} pathOptions={{ color: "#f4f4f5", fillColor: "#f4f4f5", fillOpacity: 0.7, weight: 0 }}>
                        <Popup><div className="font-mono text-xs"><div className="font-bold">{f.properties?.name}</div><div>{f.properties?.state}</div><div>Pop: {f.properties?.population}</div></div></Popup>
                    </CircleMarker>;
                })}

                {/* Shelters are drawn above villages and coloured by operational
                    status, so a CLOSED or FULL site reads as unusable at a glance
                    instead of looking like somewhere to send people. */}
                {layers.shelters && sheltersFC?.features?.map((f, i) => {
                    const c = f.geometry?.coordinates;
                    if (!c || c.length < 2) return null;
                    const p = f.properties || {};
                    const color = { OPEN: "#059669", FULL: "#ea580c", STANDBY: "#d97706", CLOSED: "#6b7280" }[p.status] || "#6b7280";
                    const free = (p.capacity != null && p.current_occupancy != null)
                        ? `${p.capacity - p.current_occupancy} of ${p.capacity} free`
                        : p.capacity != null ? "Occupancy not counted yet" : "Capacity not recorded";
                    return <CircleMarker key={`shl-${p.shelter_id || i}`} center={[c[1], c[0]]} radius={5} pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: 1.5 }}>
                        <Popup><div className="font-mono text-xs"><div className="font-bold">{p.name}</div><div>{p.status} · {p.category}</div><div>{free}</div>{p.source === "SEED_DEMO" && <div className="opacity-60">demo record</div>}</div></Popup>
                    </CircleMarker>;
                })}

                {layers.reports && reports.map((r) => (
                    <CircleMarker key={`rep-${r.id}`} center={[r.lat, r.lon]} radius={6} pathOptions={{ color: "#eab308", fillColor: "#eab308", fillOpacity: 0.75, weight: 1 }}>
                        <Popup><div className="font-mono text-xs"><div className="font-bold">{r.report_type}</div><div>{r.description}</div><div>By: {r.reporter_role}</div></div></Popup>
                    </CircleMarker>
                ))}

                <FlyTo target={focusTarget} />
            </MapContainer>

            {mapError && (
                <div className="absolute inset-x-3 top-3 z-[600] tactical-border bg-black/80 px-3 py-2 font-mono text-xs text-[var(--text-2)]">
                    GIS data is temporarily unavailable. Base map is still active.
                </div>
            )}

            {showLegend && <div className="map-overlay left-3 bottom-8" data-testid="map-legend">
                <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-1">Risk Legend</div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-mono">
                    {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((l) => <div key={l} className="flex items-center gap-1.5"><span style={{ background: SEVERITY_COLORS[l] }} className="inline-block w-3 h-3" /><span>{l}</span></div>)}
                </div>
            </div>}
        </div>
    );
}
