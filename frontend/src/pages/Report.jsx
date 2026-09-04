/**
 * Report — citizen ground truth, with a photo.
 *
 * The platform already had a reporting screen, but it lived behind
 * AuthGate roles={["ADMIN","AUTHORITY","FIELD_OFFICER"]} — so the people most
 * likely to be standing in front of a fresh crack could not use it. /public even
 * told them to "sign in before submitting a report" and then offered nowhere to
 * do it. This page closes that loop: any signed-in account, including CITIZEN,
 * can file a report with GPS and a photo.
 *
 * It stays sign-in-gated rather than fully open, and that is a deliberate
 * trade-off. Photo upload writes to storage under the user's id, and
 * corroboration counts *distinct reporters* — both of which need an identity to
 * attach to. Anonymous reporting would make the corroboration signal trivially
 * forgeable by one person with a refresh button, which would be worse than not
 * having the signal at all.
 *
 * Offline-first, because the places this matters have the worst signal: an
 * unsendable report is queued in localStorage with its photo and flushed on the
 * next connectivity event.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, auth, enqueueOffline, flushOffline, getOfflineQueue, uploadReportDataUrl } from "@/lib/api";
import {
    Camera, MapPin, WifiHigh, WifiSlash, CloudArrowUp, ArrowLeft,
    CheckCircle, Warning, Trash, PersonSimpleWalk,
} from "@phosphor-icons/react";

// Same vocabulary the field officers use, so a citizen report and an officer
// report land in one queue and one set of filters rather than two dialects.
const TYPES = [
    { id: "LANDSLIDE", label: "Landslide", hint: "Slope has already given way" },
    { id: "ROAD_BLOCKAGE", label: "Road blocked", hint: "Debris or mud across a road" },
    { id: "CRACK", label: "New crack", hint: "Fresh cracks in ground, road or wall" },
    { id: "SEEPAGE", label: "Water seepage", hint: "Water coming out of a slope face" },
    { id: "SLOPE_MOVEMENT", label: "Slope moving", hint: "Tilting poles, trees or fences" },
    { id: "ROCKFALL", label: "Rockfall", hint: "Falling or fallen boulders" },
    { id: "OTHER", label: "Something else", hint: "Anything else worth reporting" },
];

export default function Report() {
    const nav = useNavigate();
    const [online, setOnline] = useState(navigator.onLine);
    const [queueSize, setQueueSize] = useState(getOfflineQueue().length);
    const [signedIn, setSignedIn] = useState(null);      // null = still checking
    const [pos, setPos] = useState(null);
    const [locating, setLocating] = useState(false);
    const [type, setType] = useState("");
    const [description, setDescription] = useState("");
    const [photo, setPhoto] = useState(null);
    const [photoName, setPhotoName] = useState("evidence.jpg");
    const [submitting, setSubmitting] = useState(false);
    const [done, setDone] = useState(null);              // {queued:bool}
    const [msg, setMsg] = useState("");

    useEffect(() => {
        auth.session().then(({ data }) => setSignedIn(!!data?.session));
        const on = () => { setOnline(true); flushOffline().then(setQueueSize); };
        const off = () => setOnline(false);
        window.addEventListener("online", on);
        window.addEventListener("offline", off);
        if (navigator.onLine) flushOffline().then(setQueueSize);
        return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
    }, []);

    const locate = () => {
        if (!navigator.geolocation) { setMsg("This device cannot report its location."); return; }
        setLocating(true);
        navigator.geolocation.getCurrentPosition(
            (p) => { setPos({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy_m: p.coords.accuracy }); setLocating(false); setMsg(""); },
            () => { setLocating(false); setMsg("Could not read GPS. Allow location access — a report without coordinates cannot be dispatched."); },
            { enableHighAccuracy: true, timeout: 10000 },
        );
    };

    const onPhoto = (e) => {
        const f = e.target.files?.[0];
        if (!f) return;
        setPhotoName(f.name);
        const r = new FileReader();
        r.onload = () => setPhoto(r.result);
        r.readAsDataURL(f);
    };

    const submit = async () => {
        if (!pos) { setMsg("Add your location first."); return; }
        if (!type) { setMsg("Choose what you are reporting."); return; }
        setSubmitting(true); setMsg("");
        const client_uuid = crypto.randomUUID();
        const payload = { lat: pos.lat, lon: pos.lon, report_type: type, description, reporter_role: "CITIZEN", client_uuid };
        try {
            if (!online) throw new Error("offline");
            const { data } = await api.post("/reports", payload);
            const { data: sessionData } = await auth.session();
            if (photo && sessionData.session?.user?.id && data.id) {
                await uploadReportDataUrl(photo, sessionData.session.user.id, data.id, photoName);
            }
            setDone({ queued: false });
        } catch (e) {
            // Anything that stops the send — no signal, server down, timeout —
            // ends the same way: keep it on the device rather than lose it.
            enqueueOffline({ ...payload, photo_data_url: photo, photo_file_name: photoName });
            setQueueSize(getOfflineQueue().length);
            setDone({ queued: true });
        } finally { setSubmitting(false); }
    };

    const reset = () => { setDone(null); setType(""); setDescription(""); setPhoto(null); setPhotoName("evidence.jpg"); setMsg(""); };
    const flushNow = async () => setQueueSize(await flushOffline());

    // --- not signed in -------------------------------------------------------
    if (signedIn === false) {
        return (
            <div className="min-h-screen bg-[var(--bg)] flex items-center justify-center p-4" data-testid="report-signin">
                <div className="tactical-card p-6 max-w-sm text-center">
                    <PersonSimpleWalk size={28} className="mx-auto text-[var(--text-2)]" />
                    <div className="font-heading font-bold text-lg tracking-tight mt-3">Sign in to report</div>
                    <p className="text-sm text-[var(--text-2)] mt-2 leading-relaxed">
                        Reports are tied to an account so responders can follow up, and so several people
                        reporting the same thing counts as several people — not one phone pressing send twice.
                    </p>
                    <Link to="/login" className="block mt-4 py-3 bg-[var(--sev-critical)] text-white font-mono uppercase tracking-[0.15em] text-xs hover:bg-red-500">
                        Sign in or create an account
                    </Link>
                    <Link to="/safety" className="block mt-2 py-3 tactical-border font-mono uppercase tracking-[0.15em] text-xs hover:bg-white/5">
                        I need shelter directions now
                    </Link>
                </div>
            </div>
        );
    }

    // --- submitted -----------------------------------------------------------
    if (done) {
        return (
            <div className="min-h-screen bg-[var(--bg)] flex items-center justify-center p-4" data-testid="report-done">
                <div className="tactical-card p-6 max-w-sm text-center">
                    {done.queued
                        ? <CloudArrowUp size={28} className="mx-auto text-[var(--sev-medium)]" />
                        : <CheckCircle size={28} className="mx-auto text-[var(--sev-low)]" />}
                    <div className="font-heading font-bold text-lg tracking-tight mt-3">
                        {done.queued ? "Saved on your phone" : "Report sent"}
                    </div>
                    <p className="text-sm text-[var(--text-2)] mt-2 leading-relaxed">
                        {done.queued
                            ? "You have no connection right now, so the report and photo are stored on this device and will send by themselves once you have signal. You can close this page."
                            : "A responder will review it. Reports are checked before they are acted on, so you may not see it on the public map immediately."}
                    </p>
                    <button onClick={reset} data-testid="report-another" className="block w-full mt-4 py-3 tactical-border font-mono uppercase tracking-[0.15em] text-xs hover:bg-white/5">
                        Report something else
                    </button>
                    <Link to="/safety" className="block mt-2 py-3 tactical-border font-mono uppercase tracking-[0.15em] text-xs hover:bg-white/5">
                        Find a shelter
                    </Link>
                </div>
            </div>
        );
    }

    // --- the form ------------------------------------------------------------
    return (
        <div className="min-h-screen bg-[var(--bg)] pb-24" data-testid="report-page">
            <header className="sticky top-0 z-10 bg-[var(--bg)] border-b border-[var(--border)] px-4 py-3 flex items-center gap-3">
                <button onClick={() => nav("/public")} data-testid="report-back" className="text-[var(--text-2)]"><ArrowLeft size={18} /></button>
                <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">NER-SLIDE · Citizen report</div>
                    <div className="font-heading font-bold text-lg tracking-tighter">What can you see?</div>
                </div>
                <div className="ml-auto flex items-center gap-2">
                    <span className={`chip ${online ? "sev-low" : "sev-critical"}`} data-testid="report-net">
                        {online ? <WifiHigh size={11} /> : <WifiSlash size={11} />} {online ? "Online" : "Offline"}
                    </span>
                    {queueSize > 0 && (
                        <button onClick={flushNow} data-testid="report-flush" className="chip sev-medium">
                            <CloudArrowUp size={11} /> {queueSize} pending
                        </button>
                    )}
                </div>
            </header>

            <div className="p-4 space-y-4 max-w-md mx-auto">
                {!online && (
                    <div className="tactical-card p-3 flex items-start gap-2 text-xs" data-testid="report-offline-note">
                        <Warning size={14} className="text-[var(--sev-medium)] mt-[1px] shrink-0" />
                        <span>You are offline. Fill this in anyway — it will be stored on your phone and sent automatically when signal returns.</span>
                    </div>
                )}

                <div className="tactical-card p-4">
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2">1 · Where are you?</div>
                    <button onClick={locate} disabled={locating} data-testid="report-gps" className="w-full py-3 tactical-border bg-white/[0.03] font-mono uppercase tracking-[0.15em] text-sm hover:bg-white/[0.06] disabled:opacity-50 flex items-center justify-center gap-2">
                        <MapPin size={16} /> {locating ? "Finding you…" : pos ? "Update location" : "Use my location"}
                    </button>
                    {pos && (
                        <div className="mt-2 font-mono text-xs" data-testid="report-gps-value">
                            {pos.lat.toFixed(5)}, {pos.lon.toFixed(5)}
                            {pos.accuracy_m ? <span className="text-[var(--text-2)]"> · accurate to about {Math.round(pos.accuracy_m)} m</span> : null}
                        </div>
                    )}
                </div>

                <div className="tactical-card p-4">
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2">2 · What is it?</div>
                    <div className="space-y-2">
                        {TYPES.map((t) => (
                            <button
                                key={t.id}
                                data-testid={`report-type-${t.id}`}
                                onClick={() => setType(t.id)}
                                className={`w-full text-left px-3 py-2 tactical-border ${type === t.id ? "bg-[var(--sev-critical)] text-white border-[var(--sev-critical)]" : "hover:bg-white/5"}`}
                            >
                                <div className="text-sm font-heading font-bold tracking-tight">{t.label}</div>
                                <div className={`text-[11px] ${type === t.id ? "text-white/80" : "text-[var(--text-2)]"}`}>{t.hint}</div>
                            </button>
                        ))}
                    </div>
                </div>

                <div className="tactical-card p-4">
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2">3 · Photo</div>
                    <p className="text-[11px] text-[var(--text-2)] mb-2 leading-relaxed">
                        A photo is the single most useful thing you can add — it lets a responder judge the scale
                        without travelling. Only take one if it is safe to do so.
                    </p>
                    {photo ? (
                        <div data-testid="report-photo-preview">
                            <img src={photo} alt="Attached evidence" className="w-full max-h-56 object-cover tactical-border" />
                            <button onClick={() => { setPhoto(null); setPhotoName("evidence.jpg"); }} data-testid="report-photo-remove" className="mt-2 chip sev-unknown">
                                <Trash size={11} /> Remove photo
                            </button>
                        </div>
                    ) : (
                        <label className="flex items-center justify-center gap-2 py-3 tactical-border cursor-pointer hover:bg-white/5 font-mono uppercase tracking-[0.15em] text-xs">
                            <Camera size={14} /> Take or choose a photo
                            <input data-testid="report-photo" type="file" accept="image/*" capture="environment" onChange={onPhoto} className="hidden" />
                        </label>
                    )}
                </div>

                <div className="tactical-card p-4">
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-2">4 · Anything else? <span className="normal-case tracking-normal">(optional)</span></div>
                    <textarea
                        data-testid="report-desc"
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="How big is it? Is anyone hurt? Is the road passable?"
                        rows={3}
                        className="w-full tactical-border bg-transparent p-2 text-sm font-body focus:outline-none focus:border-white"
                    />
                </div>

                <button onClick={submit} disabled={submitting || !pos || !type} data-testid="report-submit" className="w-full py-4 bg-[var(--sev-critical)] text-white font-mono uppercase tracking-[0.15em] text-sm hover:bg-red-500 disabled:opacity-40">
                    {submitting ? "Sending…" : online ? "Send report" : "Save report"}
                </button>
                {msg && <div className="font-mono text-xs text-center text-[var(--sev-high)]" data-testid="report-msg">{msg}</div>}

                <p className="text-[11px] text-[var(--text-2)] text-center leading-relaxed">
                    Your report is reviewed by a responder before it is acted on. If this is a life-threatening
                    emergency, call your local emergency number first — this app is not a substitute for it.
                </p>
            </div>
        </div>
    );
}
